import asyncio
from collections import Counter
import os
import json
import argparse
from pathlib import Path
from typing import Any
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import traceback
import sys
from datetime import datetime

from dotenv import load_dotenv
_ = load_dotenv()  # take environment variables


from trae_agent.agent.selector_agent import CandidatePatch, SelectorAgent, clean_patch
from trae_agent.utils.config import Config, SelectorAgentConfig


def save_patch(instance_id: str, patches_path: str, patch: str, group_id: int):
    trial_index = 1

    dir_path = Path(patches_path) / f"group_{group_id}"
    dir_path.mkdir(parents=True, exist_ok=True)

    def get_unique_filename(trial_index: int) -> str:
        filename = f"{instance_id}_{trial_index}.patch"
        while os.path.exists(dir_path / filename):
            trial_index += 1
            filename = f"{instance_id}_{trial_index}.patch"
        return filename

    patch_file = get_unique_filename(trial_index)

    with open(dir_path / patch_file, 'w') as file:
        _ = file.write(patch)

    print(f"Patches saved in {dir_path / patch_file}")


def save_selection_success(instance_id: str, statistics_path: str, patch_id: int, is_success: int, group_id: int = 1, is_all_success: bool = False, is_all_failed: bool = False):
    dir_path = Path(statistics_path) / f"group_{group_id}"
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{instance_id}.json"

    with open(file_path, "w") as statistics_file:
        _ = statistics_file.write(json.dumps({
            "instance_id": instance_id,
            "patch_id": patch_id,
            "is_success": is_success,
            "is_all_success": is_all_success,
            "is_all_failed": is_all_failed
        }, indent=4, sort_keys=True, ensure_ascii=False))

def run_instance(*, instance: dict[str, Any], candidate_log: dict[str, Any], output_path: str, num_candidate: int, statistics_path: str, group_size: int, log_path: str, patches_path: str, majority_voting: bool = True, selector_agent_config: SelectorAgentConfig):
    # candidate_log is a list of num_candidate candidate patches
    # divide candidate_log into groups of group_size
    groups: list[Any] = []
    for i in range(0, num_candidate, group_size):
        this_group = {
            "instance_id": candidate_log["instance_id"],
            "issue": candidate_log["issue"],
            "patches": candidate_log["patches"][i:i+group_size],
            "regressions": candidate_log["regressions"][i:i+group_size],
            "success_id": candidate_log["success_id"][i:i+group_size],
        }
        groups.append(this_group)

    group_id = 0
    for group in groups:
        asyncio.run(run_instance_by_group(
            instance=instance,
            candidate_log=group,
            output_path=output_path,
            num_candidate=len(group),
            statistics_path=statistics_path,
            log_path=log_path,
            patches_path=patches_path,
            group_id=group_id,
            num_groups=len(groups),
            majority_voting=majority_voting,
            selector_agent_config=selector_agent_config,
        ))
        group_id += 1


async def run_instance_by_group(*, instance: dict[str, Any], candidate_log: dict[str, Any], output_path: str, num_candidate: int, statistics_path: str, log_path: str, patches_path: str, group_id: int, num_groups: int, majority_voting: bool = True, selector_agent_config: SelectorAgentConfig):
    print(f"[Group {group_id}/{num_groups}] processing: {instance['instance_id']}")

    # check if the group has already been processed: the statistics json file exists and is not empty
    file_path = statistics_path + f"/group_{group_id}/{instance['instance_id']}.json"
    if os.path.exists(file_path):
        if os.path.getsize(file_path) > 0:
            print(f"[Group {group_id}/{num_groups}] for instance {instance['instance_id']} has already been processed. Skipping...")
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            return
    
    # check if the group is all failed or all success. If so, skip this group
    all_failed = True
    all_success = True
    for success_id in candidate_log['success_id']:
        if success_id == 1:
            all_failed = False
        if success_id != 1:
            all_success = False
    if all_failed or all_success:
        print(f"[Group {group_id}/{num_groups}] for instance {instance['instance_id']} {'all failed' if all_failed else 'all success'}. Skipping...")
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        save_patch(instance_id=instance["instance_id"], patches_path=patches_path, patch=candidate_log['patches'][0], group_id=group_id)

        if all_failed:
            save_selection_success(instance_id=instance["instance_id"], statistics_path=statistics_path, patch_id=0, is_success=0, group_id=group_id, is_all_failed=True, is_all_success=False)
        if all_success:
            save_selection_success(instance_id=instance["instance_id"], statistics_path=statistics_path, patch_id=0, is_success=1, group_id=group_id, is_all_success=True, is_all_failed=False)

        return

    select_agent = SelectorAgent(selector_agent_config)
    log_dir_path = Path(output_path) / f"group_{group_id}"
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir_path / f"{instance['instance_id']}.log"
    log_file = open(log_file_path, 'w')
    sys.stdout = log_file
    sys.stderr = log_file

    try:
        current_try = 0
        while current_try < selector_agent_config.max_retry:
            print("current_try:", current_try)
            print("time: ", datetime.now().strftime('%Y%m%d%H%M%S'))
            current_try += 1
            trajectory = []
            sandbox = None
            try:
                candidate_list = []
                for idx in range(len(candidate_log['patches'])):
                    if candidate_log['patches'][idx].strip() == '':
                        continue
                    cleaned_patch = clean_patch(candidate_log['patches'][idx])
                    is_success_regression = len(candidate_log['regressions'][idx]) == 0
                    candidate_list.append(CandidatePatch(idx, candidate_log['patches'][idx], cleaned_patch,
                                                            is_success_regression, candidate_log['success_id'][idx]))

                # regression testing filtering
                candidate_list_regression = [candidate for candidate in candidate_list if candidate.is_success_regression]
                if len(candidate_list_regression):
                    candidate_list = candidate_list_regression
                print(f"[Retry No:{current_try}] regression testing filtering done")

                # patch deduplication
                candidate_list_deduplication, cleaned_candidate_set = [], set()
                for candidate in candidate_list:
                    if candidate.cleaned_patch not in cleaned_candidate_set:
                        cleaned_candidate_set.add(candidate.cleaned_patch)
                        candidate_list_deduplication.append(candidate)
                candidate_list = candidate_list_deduplication
                print(f"[Retry No:{current_try}] patch deduplication done")

                task = "Patch Selection"
                extra_args = {
                    "project_path": "/testbed/",
                    "problem_statement": instance["problem_statement"],
                    "candidate_record": json.dumps(candidate_log),
                }

                final_patch = ""
                final_id = -1

                # majority voting
                if majority_voting:
                    final_id_list, final_patch_list = [], []
                    for idx in range(num_candidate):
                        
                        select_agent.new_task(task, extra_args)
                        execution = await select_agent.execute_task()

                        if select_agent.final_patch is not None:
                            final_id_list.append(select_agent.final_id)
                            final_patch_list.append(select_agent.final_patch)

                        if max(Counter(final_id_list).values()) > num_candidate / 2:
                            break
                    print(f"[Retry No:{current_try}] majority voting done")

                    counter = Counter(final_id_list)
                    max_count = max(counter.values())
                    most_common_ids = [elem for elem, count in counter.items() if count == max_count]
                    result = {}
                    for id_ in most_common_ids:
                        indexes = [i for i, val in enumerate(final_id_list) if val == id_]
                        result[id_] = indexes
                    final_id = most_common_ids[0]
                    final_patch = final_patch_list[result[final_id][0]]
                    print(f"[Retry No:{current_try}] final_id_list: {final_id_list}")
                else:
                    select_agent.new_task(task, extra_args)
                    execution = await select_agent.execute_task()

                    if select_agent.final_patch is not None:
                        final_id = select_agent.final_id
                        final_patch = select_agent.final_patch

                save_patch(instance_id=instance["instance_id"], patches_path=patches_path, patch=final_patch, group_id=group_id)

                is_success_patch = 0
                for candidate in candidate_list:
                    if final_id == candidate.id:
                        is_success_patch = candidate.is_success_patch
                save_selection_success(instance_id=instance["instance_id"], statistics_path=statistics_path, patch_id=final_id, is_success=is_success_patch, group_id=group_id)
                break
            except Exception as e:
                print(f"Error occurred: {e}")
                print("Detailed Error:\n", traceback.format_exc())
                if sandbox is not None:
                    sandbox.stop_container()
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        print(f"         finished: {instance["instance_id"]}")




class SelectorEvaluation:
    def __init__(
        self,
        *,
        selector_agent_config: SelectorAgentConfig,
        num_candidate: int,
        log_path: str,
        output_path: str,
        patches_path: str,
        instance_list: list[dict[str, Any]],
        candidate_dic: dict[str, dict[str, Any]],
        statistics_path: str,
        group_size: int,
        majority_voting: bool = True
    ):
        self.selector_agent_config = selector_agent_config
        self.num_candidate = num_candidate
        self.log_path = log_path
        self.output_path = output_path
        self.patches_path = patches_path
        self.instance_list = instance_list
        self.candidate_dic = candidate_dic
        self.statistics_path = statistics_path
        self.group_size = group_size
        self.majority_voting = majority_voting

    def run_all(self, max_workers=None):
        """Run all instances concurrently using ThreadPoolExecutor.
        
        Args:
            max_workers: Maximum number of worker threads. If None, defaults to min(32, os.cpu_count() + 4)
        """
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(run_instance, instance=instance, candidate_log=self.candidate_dic[instance['instance_id']], output_path=self.output_path, num_candidate=self.num_candidate, statistics_path=self.statistics_path, group_size=self.group_size, log_path=self.log_path, patches_path=self.patches_path, majority_voting=self.majority_voting, selector_agent_config=self.selector_agent_config): instance['instance_id'] for instance in self.instance_list
            }

            with tqdm(total=len(futures), ascii=True, desc="Processing instances") as pbar:
                for fut in as_completed(futures):
                    iid = futures[fut]
                    try:
                        result_iid = fut.result()
                        pbar.set_postfix({"completed": result_iid})
                    except Exception as e:
                        result_iid = iid
                        print(traceback.format_exc())
                    finally:
                        pbar.update(1)

    def run_one(self, instance_id):
        for idx in range(len(self.instance_list)):
            if instance_id == self.instance_list[idx]["instance_id"]:
                run_instance(instance=self.instance_list[idx], candidate_log=self.candidate_dic[instance_id], output_path=self.output_path, num_candidate=self.num_candidate, statistics_path=self.statistics_path, group_size=self.group_size, log_path=self.log_path, patches_path=self.patches_path, majority_voting=self.majority_voting, selector_agent_config=self.selector_agent_config)


def main():
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--instances_path", required=True, help="Path to instances JSON file (e.g. swebench-verified.json)")
    _ = parser.add_argument("--candidate_path", required=True, help="Path to candidate patches")
    _ = parser.add_argument("--result_path", required=True, help="Path to save results")
    _ = parser.add_argument("--num_candidate", type=int, default=10, help="The number of candidate patches")
    _ = parser.add_argument("--group_size", type=int, default=10, help="Group size of candidate patches")
    _ = parser.add_argument("--max_retry", type=int, default=3, help="Max retry times of LLM responses")
    _ = parser.add_argument("--max_turn", type=int, default=50, help="Max turn times of Selector Agent")
    _ = parser.add_argument('--majority_voting', action=argparse.BooleanOptionalAction, description="Use majority voting to select the best patch")
    _ = parser.add_argument('--config_file', type=str, default="trae_config.yaml", help="Config file to use")
    _ = parser.add_argument('--instance_id', type=str, required=True, help="Instance ID")
    args = parser.parse_args()
    args.log_path = os.path.join(args.result_path, 'log')
    args.output_path = os.path.join(args.result_path, 'output')
    args.patches_path = os.path.join(args.result_path, 'patch')
    args.statistics_path = os.path.join(args.result_path, 'statistics')
    [os.makedirs(_) for _ in [args.log_path, args.patches_path, args.output_path, args.statistics_path] if not os.path.exists(_)]

    with open(args.instances_path, 'r') as file:
        instance_list: list[dict[str, Any]] = json.load(file)

    trae_config = Config.create(config_file=args.config_file)
    
    if trae_config.selector_agent is None:
        raise ValueError("Selector agent config is not provided")
    selector_agent_config = trae_config.selector_agent
    
    candidate_dic = {}
    with open(args.candidate_path, "r") as file:
        for line in file.readlines():
            candidate = json.loads(line.strip())
            if "regressions" not in candidate:
                candidate["regressions"] = []
                for _ in range(len(candidate["patches"])):
                    candidate["regressions"].append([])
            candidate_dic[candidate["instance_id"]] = candidate

    try:
        log_path = Path(args.log_path)
        log_path.mkdir(parents=True, exist_ok=True)
    except:
        print(f'Error creating log path for {args.log_path}')
        exit()

    evaluation = SelectorEvaluation(
        selector_agent_config=selector_agent_config,
        num_candidate=args.num_candidate,
        log_path=args.log_path,
        output_path=args.output_path,
        patches_path=args.patches_path,
        instance_list=instance_list,
        candidate_dic=candidate_dic,
        statistics_path=args.statistics_path,
        group_size=args.group_size,
        majority_voting=args.majority_voting
    )

    evaluation.run_one(args.instance_id)


if __name__ == "__main__":
    main()