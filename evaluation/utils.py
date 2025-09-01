# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from datasets import load_dataset
from docker.models.containers import Container, ExecResult


def docker_exec(container: Container, command: str):
    """
    Execute a shell command inside a Docker container.

    Args:
        container: Docker container object.
        command: Shell command to execute.

    Returns:
        Tuple (return_code, output_str).
    """
    exec_result: ExecResult = container.exec_run(cmd=command)
    return_code = exec_result[0]
    output = exec_result[1].decode("utf-8")
    return return_code, output


def swebench_evaluate_harness_after(benchmark_harness_path, task_id):
    src_base = f"{benchmark_harness_path}/logs/run_evaluation/{task_id}/trae-agent"
    dst_base = f"results/{task_id}"
    json_src = f"{benchmark_harness_path}/trae-agent.{task_id}.json"
    json_dst = os.path.join(dst_base, "results.json")
    if not os.path.exists(src_base):
        print(f"Source directory does not exist: {src_base}")
        return
    for folder_name in os.listdir(src_base):
        src_folder = os.path.join(src_base, folder_name)
        dst_folder = os.path.join(dst_base, folder_name)
        if os.path.isdir(src_folder):
            os.makedirs(dst_folder, exist_ok=True)
            for file_name in os.listdir(src_folder):
                src_file = os.path.join(src_folder, file_name)
                dst_file = os.path.join(dst_folder, file_name)
                if not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)
    os.makedirs(dst_base, exist_ok=True)
    if not os.path.exists(json_dst):
        shutil.copy2(json_src, json_dst)


def multi_swebench_evaluate_harness_after(benchmark_harness_path, task_id):
    task_results_dir = Path("results") / task_id
    output_dir = (task_results_dir / "dataset").resolve()
    src_file = output_dir / "final_report.json"
    dst_file = task_results_dir / "results.json"
    if not src_file.exists():
        raise FileNotFoundError(f"{src_file} not found")
    shutil.copyfile(src_file, dst_file)


def _write_problem_statement(instance_dir: Path, content: str) -> int:
    """Helper function to write problem statement using context manager."""
    with open(instance_dir / "problem_statement.txt", "w", encoding="utf-8") as f:
        return f.write(content)


def _load_jsonl_dataset(dataset_name: str) -> list[dict]:
    """Helper function to load JSONL dataset using context manager."""
    result = []
    with open(f"{dataset_name.lower().replace('-', '_')}.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                result.append(json.loads(line))
    return result


def _write_multi_problem_statement(instance_dir: Path, resolved_issues: list[dict]) -> int:
    """Helper function to write multi-issue problem statement using context manager."""
    content = "\n".join(
        issue.get("title", "") + "\n" + issue.get("body", "") for issue in resolved_issues
    )
    with open(instance_dir / "problem_statement.txt", "w", encoding="utf-8") as f:
        return f.write(content)


def multi_swebench_evaluate_harness_before(task_results_dir, dataset_name, max_workers):
    task_results_dir = Path(task_results_dir)
    pred_json_path = task_results_dir / "predictions.json"
    pred_jsonl_path = task_results_dir / "predictions.jsonl"
    dataset_file_path = f"{dataset_name.lower().replace('-', '_')}.jsonl"

    instance_map = {}
    with open(dataset_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            instance_id = item.get("instance_id")
            org = item.get("org")
            repo = item.get("repo")
            number = item.get("number")
            instance_map[instance_id] = {"org": org, "repo": repo, "number": number}

    with open(pred_json_path, "r", encoding="utf-8") as f:
        preds = json.load(f)
    with open(pred_jsonl_path, "w", encoding="utf-8") as f:
        for item in preds:
            instance_id = item["instance_id"]
            patch = item["model_patch"]
            info = instance_map.get(instance_id, {})
            new_item = {
                "org": info.get("org"),
                "repo": info.get("repo"),
                "number": info.get("number"),
                "fix_patch": patch,
            }
            f.write(json.dumps(new_item, ensure_ascii=False) + "\n")

    base_dir = Path(__file__).resolve().parent
    task_results_dir = base_dir / task_results_dir
    patch_file_path = str((base_dir / pred_jsonl_path).resolve())
    dataset_file_path = str((base_dir / dataset_file_path).resolve())

    output_dir = (task_results_dir / "dataset").resolve()
    repo_dir = (task_results_dir / "repos").resolve()
    log_dir = (task_results_dir / "logs").resolve()
    workdir = (task_results_dir / "workdir").resolve()

    output_dir.mkdir(parents=True, exist_ok=True)
    repo_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    output_dir = str(output_dir)
    repo_dir = str(repo_dir)
    log_dir = str(log_dir)
    workdir = str(workdir)

    config = {
        "mode": "evaluation",
        "workdir": workdir,
        "patch_files": [patch_file_path],
        "dataset_files": [dataset_file_path],
        "force_build": False,
        "output_dir": output_dir,
        "specifics": [],
        "skips": [],
        "repo_dir": repo_dir,
        "need_clone": False,
        "global_env": [],
        "clear_env": True,
        "stop_on_error": True,
        "max_workers": max_workers,
        "max_workers_build_image": max_workers,
        "max_workers_run_instance": max_workers,
        "log_dir": log_dir,
        "log_level": "DEBUG",
    }

    config_path = task_results_dir / "evaluate_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


@dataclass
class BenchmarkConfig:
    valid_datasets: list[str]
    load_dataset: Callable[[str], Any]
    image_name: Callable[[str], str]
    problem_statement: Callable[[dict, Path], Any]
    working_dir: Callable[[str], str]
    evaluate_harness: Callable[..., list[str]]
    evaluate_harness_before: Callable[..., Any]
    evaluate_harness_after: Callable[..., Any]


BENCHMARK_CONFIG: dict[str, BenchmarkConfig] = {
    # SWE-bench
    "SWE-bench": BenchmarkConfig(
        valid_datasets=["SWE-bench", "SWE-bench_Lite", "SWE-bench_Verified"],
        load_dataset=lambda dataset_name: load_dataset(
            f"princeton-nlp/{dataset_name}", split="test"
        ),
        image_name=lambda instance_id: (
            f"swebench/sweb.eval.x86_64.{instance_id.lower()}:latest".replace("__", "_1776_")
        ),
        problem_statement=lambda instance, instance_dir: (
            _write_problem_statement(instance_dir, instance.get("problem_statement", ""))
        ),
        working_dir=lambda instance_id: "/testbed/",
        evaluate_harness=lambda dataset_name, task_results_dir, task_id, max_workers: [
            "swebench_venv/bin/python",
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            f"princeton-nlp/{dataset_name}",
            "--predictions_path",
            (task_results_dir / "predictions.json").absolute().as_posix(),
            "--max_workers",
            str(max_workers),
            "--run_id",
            task_id,
            "--cache_level",
            "instance",
            "--instance_image_tag",
            "latest",
        ],
        evaluate_harness_before=lambda *args, **kwargs: None,
        evaluate_harness_after=swebench_evaluate_harness_after,
    ),
    # SWE-bench-Live
    "SWE-bench-Live": BenchmarkConfig(
        valid_datasets=["SWE-bench-Live/lite", "SWE-bench-Live/verified", "SWE-bench-Live/full"],
        load_dataset=lambda dataset_name: load_dataset(
            "SWE-bench-Live/SWE-bench-Live", split=dataset_name.split("/")[-1]
        ),
        image_name=lambda instance_id: (
            f"starryzhang/sweb.eval.x86_64.{instance_id.lower()}:latest".replace("__", "_1776_")
        ),
        problem_statement=lambda instance, instance_dir: (
            _write_problem_statement(instance_dir, instance.get("problem_statement", ""))
        ),
        working_dir=lambda instance_id: "/testbed/",
        evaluate_harness=lambda dataset_name, task_results_dir, task_id, max_workers: [
            "swebench_live_venv/bin/python",
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            "SWE-bench-Live/SWE-bench-Live",
            "--namespace",
            "starryzhang",
            "--split",
            dataset_name.split("/")[-1],
            "--predictions_path",
            (task_results_dir / "predictions.json").absolute().as_posix(),
            "--run_id",
            task_id,
            "--max_workers",
            str(max_workers),
        ],
        evaluate_harness_before=lambda *args, **kwargs: None,
        evaluate_harness_after=swebench_evaluate_harness_after,
    ),
    # Multi-SWE-bench
    "Multi-SWE-bench": BenchmarkConfig(
        valid_datasets=["Multi-SWE-bench-flash", "Multi-SWE-bench_mini"],
        load_dataset=lambda dataset_name: _load_jsonl_dataset(dataset_name),
        image_name=lambda instance_id: (
            (lambda key: key.rpartition("-")[0] + ":pr-" + key.rpartition("-")[2])(
                f"mswebench/{instance_id.lower()}".replace("__", "_m_")
            )
        ),
        problem_statement=lambda instance, instance_dir: (
            _write_multi_problem_statement(instance_dir, instance.get("resolved_issues", []))
        ),
        working_dir=lambda instance_id: (
            f"/home/{'-'.join(instance_id.split('__')[-1].split('-')[:-1])}/"
        ),
        evaluate_harness=lambda dataset_name, task_results_dir, task_id, max_workers: [
            "multi_swebench_venv/bin/python",
            "-m",
            "multi_swe_bench.harness.run_evaluation",
            "--config",
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                task_results_dir / "evaluate_config.json",
            ),
        ],
        evaluate_harness_before=multi_swebench_evaluate_harness_before,
        evaluate_harness_after=multi_swebench_evaluate_harness_after,
    ),
}
