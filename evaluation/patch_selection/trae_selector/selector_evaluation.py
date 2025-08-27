import os
import sys
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from trae_agent.utils.config import ModelConfig

from .sandbox import Sandbox
from .selector_agent import CandidatePatch, SelectorAgent
from .utils import clean_patch, get_trajectory_filename, save_patches, save_selection_success


def run_instance(
    *,
    instance,
    candidate_log,
    output_path,
    max_retry,
    num_candidate,
    tools_path,
    statistics_path,
    group_size,
    llm_config,
    max_turn,
    log_path,
    patches_path,
    majority_voting=True,
):
    # candidate_log is a list of num_candidate candidate patches
    # divide candidate_log into groups of group_size
    groups = []
    for i in range(0, num_candidate, group_size):
        this_group = {
            "instance_id": candidate_log["instance_id"],
            "issue": candidate_log["issue"],
            "patches": candidate_log["patches"][i : i + group_size],
            "regressions": candidate_log["regressions"][i : i + group_size],
            "success_id": candidate_log["success_id"][i : i + group_size],
        }
        groups.append(this_group)

    for group_id, group in enumerate(groups):
        run_instance_by_group(
            instance=instance,
            candidate_log=group,
            output_path=output_path,
            max_retry=max_retry,
            num_candidate=len(group),
            tools_path=tools_path,
            statistics_path=statistics_path,
            llm_config=llm_config,
            max_turn=max_turn,
            log_path=log_path,
            patches_path=patches_path,
            group_id=group_id,
            num_groups=len(groups),
            majority_voting=majority_voting,
        )


def run_instance_by_group(
    *,
    instance,
    candidate_log,
    output_path,
    max_retry,
    num_candidate,
    tools_path,
    statistics_path,
    llm_config,
    max_turn,
    log_path,
    patches_path,
    group_id,
    num_groups,
    majority_voting=True,
):
    print(f"[Group {group_id}/{num_groups}] processing: {instance['instance_id']}")
    sys.stdout.flush()
    sys.stderr.flush()

    # check if the group has already been processed: the statistics json file exists and is not empty
    file_path = statistics_path + f"/group_{group_id}/{instance['instance_id']}.json"
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        print(
            f"[Group {group_id}/{num_groups}] for instance {instance['instance_id']} has already been processed. Skipping..."
        )
        sys.stdout.flush()
        sys.stderr.flush()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        return

    # check if the group is all failed or all success. If so, skip this group
    all_failed = True
    all_success = True
    for success_id in candidate_log["success_id"]:
        if success_id == 1:
            all_failed = False
        if success_id != 1:
            all_success = False
    if all_failed or all_success:
        print(
            f"[Group ID {group_id} in {num_groups}] groups for instance {instance['instance_id']} {'all failed' if all_failed else 'all success'}. Skipping..."
        )
        sys.stdout.flush()
        sys.stderr.flush()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        save_patches(
            instance_id=instance["instance_id"],
            patches_path=patches_path,
            patches=candidate_log["patches"][0],
            group_id=group_id,
        )

        if all_failed:
            save_selection_success(
                instance_id=instance["instance_id"],
                statistics_path=statistics_path,
                patch_id=0,
                is_success=0,
                group_id=group_id,
                is_all_failed=True,
                is_all_success=False,
            )
        if all_success:
            save_selection_success(
                instance_id=instance["instance_id"],
                statistics_path=statistics_path,
                patch_id=0,
                is_success=1,
                group_id=group_id,
                is_all_success=True,
                is_all_failed=False,
            )

        return

    log_dir_path = Path(output_path) / f"group_{group_id}"
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir_path / f"{instance['instance_id']}.log"
    with open(log_file_path, "w") as log_file:
        sys.stdout = log_file
        sys.stderr = log_file
        namespace = "swebench"
        image_name = "sweb.eval.x86_64." + instance["instance_id"].replace("__", "_1776_")
        tag = "latest"

        try:
            current_try = 0
            while current_try < max_retry:
                print("current_try:", current_try)
                sys.stdout.flush()
                sys.stderr.flush()
                print("time: ", datetime.now().strftime("%Y%m%d%H%M%S"))
                sys.stdout.flush()
                sys.stderr.flush()
                current_try += 1
                sandbox = None
                try:
                    candidate_list = []
                    for idx in range(len(candidate_log["patches"])):
                        if candidate_log["patches"][idx].strip() == "":
                            continue
                        cleaned_patch = clean_patch(candidate_log["patches"][idx])
                        is_success_regression = len(candidate_log["regressions"][idx]) == 0
                        candidate_list.append(
                            CandidatePatch(
                                idx,
                                candidate_log["patches"][idx],
                                cleaned_patch,
                                is_success_regression,
                                candidate_log["success_id"][idx],
                            )
                        )

                    # regression testing
                    candidate_list_regression = [
                        candidate for candidate in candidate_list if candidate.is_success_regression
                    ]
                    if len(candidate_list_regression):
                        candidate_list = candidate_list_regression
                    print(f"[Retry No:{current_try}] regression testing done")
                    sys.stdout.flush()
                    sys.stderr.flush()

                    # patch deduplication
                    candidate_list_deduplication, cleaned_candidate_set = [], set()
                    for candidate in candidate_list:
                        if candidate.cleaned_patch not in cleaned_candidate_set:
                            cleaned_candidate_set.add(candidate.cleaned_patch)
                            candidate_list_deduplication.append(candidate)
                    candidate_list = candidate_list_deduplication
                    print(f"[Retry No:{current_try}] patch deduplication done")
                    sys.stdout.flush()
                    sys.stderr.flush()

                    # sandbox & tools
                    sandbox = Sandbox(namespace, image_name, tag, instance, tools_path)
                    sandbox.start_container()
                    project_path = sandbox.get_project_path()
                    print(f"[Retry No:{current_try}] sandbox & tools done")
                    sys.stdout.flush()
                    sys.stderr.flush()

                    # majority voting
                    if majority_voting:
                        final_id_list, final_patch_list = [], []
                        for idx in range(num_candidate):
                            select_agent = SelectorAgent(
                                llm_config=llm_config,
                                sandbox=sandbox,
                                project_path=project_path,
                                issue_description=instance["problem_statement"],
                                trajectory_file_name=get_trajectory_filename(
                                    instance["instance_id"], log_path, group_id, idx
                                ),
                                candidate_list=candidate_list,
                                max_turn=max_turn,
                            )

                            final_id, final_patch = select_agent.run()
                            final_id_list.append(final_id)
                            final_patch_list.append(final_patch)
                            if max(Counter(final_id_list).values()) > num_candidate / 2:
                                break
                        print(f"[Retry No:{current_try}] majority voting done")
                        sys.stdout.flush()
                        sys.stderr.flush()

                        counter = Counter(final_id_list)
                        max_count = max(counter.values())
                        most_common_ids = [
                            elem for elem, count in counter.items() if count == max_count
                        ]
                        result = {}
                        for id_ in most_common_ids:
                            indexes = [i for i, val in enumerate(final_id_list) if val == id_]
                            result[id_] = indexes
                        final_id = most_common_ids[0]
                        final_patch = final_patch_list[result[final_id][0]]
                        print(f"[Retry No:{current_try}] final_id_list: {final_id_list}")
                        sys.stdout.flush()
                        sys.stderr.flush()
                    else:
                        select_agent = SelectorAgent(
                            llm_config=llm_config,
                            sandbox=sandbox,
                            project_path=project_path,
                            issue_description=instance["problem_statement"],
                            trajectory_file_name=get_trajectory_filename(
                                instance["instance_id"], log_path, group_id, 0
                            ),
                            candidate_list=candidate_list,
                            max_turn=max_turn,
                        )
                        final_id, final_patch = select_agent.run()
                    save_patches(
                        instance_id=instance["instance_id"],
                        patches_path=patches_path,
                        patches=final_patch,
                        group_id=group_id,
                    )

                    is_success_patch = 0
                    for candidate in candidate_list:
                        if final_id == candidate.id:
                            is_success_patch = candidate.is_success_patch
                    save_selection_success(
                        instance_id=instance["instance_id"],
                        statistics_path=statistics_path,
                        patch_id=final_id,
                        is_success=is_success_patch,
                        group_id=group_id,
                    )
                    sandbox.stop_container()
                    break
                except Exception as e:
                    print(f"Error occurred: {e}")
                    sys.stdout.flush()
                    sys.stderr.flush()
                    print("Detailed Error:\n", traceback.format_exc())
                    sys.stdout.flush()
                    sys.stderr.flush()
                    if sandbox is not None:
                        sandbox.stop_container()
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            print(f"         finished: {instance['instance_id']}")


class SelectorEvaluation:
    def __init__(
        self,
        llm_config: ModelConfig,
        num_candidate: int,
        max_retry: int,
        max_turn: int,
        log_path: str,
        output_path: str,
        patches_path: str,
        instance_list: list,
        candidate_dic: dict[str, dict],
        tools_path: str,
        statistics_path: str,
        group_size: int,
        majority_voting: bool = True,
    ):
        self.llm_config = llm_config
        self.num_candidate = num_candidate
        self.max_retry = max_retry
        self.log_path = log_path
        self.output_path = output_path
        self.patches_path = patches_path
        self.instance_list = instance_list
        self.candidate_dic = candidate_dic
        self.max_turn = max_turn
        self.tools_path = tools_path
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
                ex.submit(
                    run_instance,
                    instance=instance,
                    candidate_log=self.candidate_dic[instance["instance_id"]],
                    output_path=self.output_path,
                    max_retry=self.max_retry,
                    num_candidate=self.num_candidate,
                    tools_path=self.tools_path,
                    statistics_path=self.statistics_path,
                    group_size=self.group_size,
                    llm_config=self.llm_config,
                    max_turn=self.max_turn,
                    log_path=self.log_path,
                    patches_path=self.patches_path,
                    majority_voting=self.majority_voting,
                ): instance["instance_id"]
                for instance in self.instance_list
            }

            with tqdm(total=len(futures), ascii=True, desc="Processing instances") as pbar:
                for fut in as_completed(futures):
                    iid = futures[fut]
                    try:
                        result_iid = fut.result()
                        pbar.set_postfix({"completed": result_iid})
                    except Exception:
                        result_iid = iid
                        print(traceback.format_exc())
                        sys.stdout.flush()
                        sys.stderr.flush()
                    finally:
                        pbar.update(1)

    def run_one(self, instance_id):
        for idx in range(len(self.instance_list)):
            if instance_id == self.instance_list[idx]["instance_id"]:
                run_instance(
                    instance=self.instance_list[idx],
                    candidate_log=self.candidate_dic[instance_id],
                    output_path=self.output_path,
                    max_retry=self.max_retry,
                    num_candidate=self.num_candidate,
                    tools_path=self.tools_path,
                    statistics_path=self.statistics_path,
                    group_size=self.group_size,
                    llm_config=self.llm_config,
                    max_turn=self.max_turn,
                    log_path=self.log_path,
                    patches_path=self.patches_path,
                    majority_voting=self.majority_voting,
                )
