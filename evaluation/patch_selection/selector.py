import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from trae_selector.selector_evaluation import SelectorEvaluation

from trae_agent.utils.config import Config

_ = load_dotenv()  # take environment variables


def main():
    parser = argparse.ArgumentParser()
    _ = parser.add_argument(
        "--instances_path",
        default="swe_bench/swebench-verified.json",
        help="Path to instances JSON file",
    )
    _ = parser.add_argument("--candidate_path", required=True, help="Path to candidate patches")
    _ = parser.add_argument("--result_path", required=True, help="Path to save results")
    _ = parser.add_argument(
        "--num_candidate", type=int, default=10, help="The number of candidate patches"
    )
    _ = parser.add_argument("--max_workers", type=int, default=10, help="Max number of workers")
    _ = parser.add_argument(
        "--group_size", type=int, default=10, help="Group size of candidate patches"
    )
    _ = parser.add_argument(
        "--max_retry", type=int, default=3, help="Max retry times of LLM responses"
    )
    _ = parser.add_argument(
        "--max_turn", type=int, default=50, help="Max turn times of Selector Agent"
    )
    _ = parser.add_argument("--majority_voting", action=argparse.BooleanOptionalAction)
    _ = parser.add_argument(
        "--config_file", type=str, default="config.yaml", help="Path to config file"
    )
    _ = parser.add_argument("--model_name", type=str, default="default_model", help="Model name")
    args = parser.parse_args()
    args.log_path = os.path.join(args.result_path, "log")
    args.output_path = os.path.join(args.result_path, "output")
    args.patches_path = os.path.join(args.result_path, "patch")
    args.statistics_path = os.path.join(args.result_path, "statistics")
    [
        os.makedirs(_)
        for _ in [args.log_path, args.patches_path, args.output_path, args.statistics_path]
        if not os.path.exists(_)
    ]

    with open(args.instances_path, "r") as file:
        instance_list = json.load(file)
    config = Config.create(config_file=args.config_file)
    if not config.models:
        raise ValueError("No models found in config file.")
    if args.model_name not in config.models:
        raise ValueError(f"Model {args.model_name} not found in config file.")
    llm_config = config.models[args.model_name]
    llm_config.resolve_config_values()

    candidate_dic = {}
    with open(args.candidate_path, "r") as file:
        for line in file.readlines():
            candidate = json.loads(line.strip())
            if "regressions" not in candidate:
                candidate["regressions"] = []
                for _ in range(len(candidate["patches"])):
                    candidate["regressions"].append([])
            candidate_dic[candidate["instance_id"]] = candidate

    tools_path = Path(__file__).parent / "trae_selector/tools"

    try:
        log_path = Path(args.log_path)
        log_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        print(f"Error creating log path for {args.log_path}")
        exit()

    evaluation = SelectorEvaluation(
        llm_config,
        args.num_candidate,
        args.max_retry,
        args.max_turn,
        args.log_path,
        args.output_path,
        args.patches_path,
        instance_list,
        candidate_dic,
        tools_path.as_posix(),
        args.statistics_path,
        args.group_size,
        majority_voting=args.majority_voting,
    )

    # evaluation.run_one("astropy__astropy-14369")
    evaluation.run_all(max_workers=args.max_workers)


if __name__ == "__main__":
    main()
