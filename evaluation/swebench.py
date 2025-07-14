# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import argparse
import json
import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Any

from datasets import load_dataset  # pyright: ignore
from docker import DockerClient, from_env
from docker.errors import ImageNotFound
from docker.models.containers import Container, ExecResult
from tqdm import tqdm


def docker_exec(container: Container, command: str):
    """
    Execute a command in a docker container.

    Args:
        container: The docker container object.
        command: The command to execute.

    Returns:
        A tuple of (return_code, output).
    """
    exec_result: ExecResult = container.exec_run(cmd=command)  # pyright: ignore[reportUnknownMemberType]
    return_code = exec_result[0]
    output = exec_result[1].decode("utf-8")
    return return_code, output


class SWEBenchEvaluation:
    def __init__(
        self,
        working_dir: str,
        trae_config_file_name: str,
        dataset: str = "SWE-bench_Verified",
        docker_env_config: str = "",
        swebench_harness_path: str = "",
        run_id: str = "trae-agent",
    ):
        """
        Initialize the SWEBenchEvaluation class. The initialisation includes checking the existence of required Docker images and downloading missing images.

        Args:
            working_dir: The working directory.
            trae_config_file_name: The path to the Trae config file.
            dataset: The dataset to evaluate.
            docker_env_config: The path to the docker environment config file.
            swebench_harness_path: The path to the SWEBench harness.
            run_id: The run id.
        """
        assert dataset in ["SWE-bench", "SWE-bench_Lite", "SWE-bench_Verified"], (
            f"Invalid dataset name: {dataset}"
        )
        self.dataset = load_dataset(f"princeton-nlp/{dataset}", split="test")
        self.dataset_name = dataset

        self.docker_client: DockerClient = from_env()
        self.image_status: dict[Any, Any] = {}
        self.working_dir = Path(working_dir)
        self.swebench_harness_path = swebench_harness_path
        self.run_id = run_id

        if docker_env_config != "":
            with open(docker_env_config, "r") as f:
                self.docker_env_config: dict[str, dict[str, str]] = json.load(f)
        else:
            self.docker_env_config = {}

        if not self.working_dir.exists():
            self.working_dir.mkdir(parents=True, exist_ok=True)

        self.trae_config_file_name = trae_config_file_name

        shutil.copyfile(self.trae_config_file_name, self.working_dir / "trae_config_local.json")

        self.pull_images()

    def _image_name(self, instance_id: str) -> str:
        """
        Get the image name from the instance id.

        Args:
            instance_id: The instance id.

        Returns:
            The image name.
        """
        key = f"swebench/sweb.eval.x86_64.{instance_id.lower()}:latest"
        key = key.replace("__", "_1776_")
        return key

    def _check_images(self):
        """
        Check the existence of required Docker images.
        """
        for item in tqdm(self.dataset, desc="Checking image status"):  # pyright: ignore[reportUnknownVariableType]
            instance_id: str = item["instance_id"]  # pyright: ignore[reportUnknownVariableType]
            image_name = self._image_name(instance_id)  # pyright: ignore[reportUnknownArgumentType]
            try:
                _ = self.docker_client.images.get(image_name)
                self.image_status[instance_id] = True
            except ImageNotFound:
                self.image_status[instance_id] = False
        try:
            _ = self.docker_client.images.get("ubuntu:22.04")
        except Exception:
            self.docker_client.images.pull("ubuntu:22.04")

    def pull_images(self):
        """
        Pull the required Docker images.
        """
        self._check_images()
        print(f"Total number of images: {len(self.image_status)}")
        instance_ids = [
            instance_id for instance_id in self.image_status if not self.image_status[instance_id]
        ]
        print(f"Number of images to download: {len(instance_ids)}")
        if len(instance_ids) == 0:
            return
        for instance_id in tqdm(instance_ids, desc="Downloading images"):
            image_name = self._image_name(instance_id)
            self.docker_client.images.pull(image_name)

    def prepare_trae_agent(self):
        """
        Prepare the Trae agent by building Trae Agent and UV inside a general Ubuntu image, save the artifacts in the workspace, which are then used in experiment Docker containers.
        """
        tars = ["trae-agent.tar", "uv.tar", "uv_shared.tar"]
        all_exist = True
        for tar in tars:
            tar_path = self.working_dir / tar
            if not tar_path.exists():
                all_exist = False
                break

        if all_exist:
            print("Found built trae-agent and uv artifacts. Skipping building.")
            return

        try:
            image = self.docker_client.images.get("ubuntu:22.04")
        except Exception:
            image = self.docker_client.images.pull("ubuntu:22.04")

        container = self.docker_client.containers.run(
            image=image,
            command="bash",
            detach=True,
            tty=True,
            stdin_open=True,
            volumes={
                self.working_dir.absolute().as_posix(): {"bind": "/trae-workspace", "mode": "rw"}
            },
            environment=self.docker_env_config.get("preparation_env", None),  # pyright: ignore[reportUnknownMemberType]
        )

        commands = [
            "apt-get update",
            "apt-get install -y curl git",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "git clone https://github.com/bytedance/trae-agent.git /trae-workspace/trae-agent",
            "cd /trae-workspace/trae-agent && source $HOME/.local/bin/env && uv sync",
        ]

        for command in tqdm(commands, desc="Building trae-agent inside base Docker container"):
            try:
                new_command = f'/bin/bash -c "{command}"'
                return_code, output = docker_exec(container, new_command)
            except Exception:
                print(f"{command} failed.")
                print(traceback.format_exc())
                break
            if return_code is not None and return_code != 0:
                print("Docker exec error. Error message: {}".format(output))
                exit(-1)

        with open(self.working_dir / "trae-agent.tar", "wb") as f:
            bits, _ = container.get_archive("/trae-workspace/trae-agent")
            for chunk in bits:
                f.write(chunk)

        with open(self.working_dir / "uv.tar", "wb") as f:
            bits, _ = container.get_archive("/root/.local/bin/uv")
            for chunk in bits:
                f.write(chunk)

        with open(self.working_dir / "uv_shared.tar", "wb") as f:
            bits, _ = container.get_archive("/root/.local/share/uv")
            for chunk in bits:
                f.write(chunk)

        container.stop()
        container.remove()

    def prepare_experiment_container(self, instance: dict[str, str]) -> Container:
        """
        Prepare an experiment Docker container for a given instance.

        Args:
            instance: A dictionary containing instance information.

        Returns:
            The Docker container object.
        """
        image_name = self._image_name(instance["instance_id"])

        instance_dir = self.working_dir / instance["instance_id"]
        instance_dir.mkdir(parents=True, exist_ok=True)

        with open(instance_dir / "problem_statement.txt", "w") as f:
            f.write(instance["problem_statement"])

        container: Container = self.docker_client.containers.run(
            image_name,
            command="/bin/bash",
            detach=True,
            tty=True,
            stdin_open=True,
            volumes={
                self.working_dir.absolute().as_posix(): {"bind": "/trae-workspace", "mode": "rw"}
            },
            working_dir="/trae-workspace",
            environment=self.docker_env_config.get("experiment_env", None),
            stream=True,
        )

        commands = [
            "tar xf trae-agent.tar",
            "tar xf uv.tar",
            "mkdir -p /root/.local/bin",
            "mv uv /root/.local/bin/",
            "tar xf uv_shared.tar",
            "mkdir -p /root/.local/share",
            "mv uv /root/.local/share/",
        ]

        for command in commands:
            try:
                new_command = f'/bin/bash -c "{command}"'
                return_code, output = docker_exec(container, new_command)
                if return_code is not None and return_code != 0:
                    print("Docker exec error. Error message: {}".format(output))
            except Exception:
                print(f"{command} failed.")
                print(traceback.format_exc())
                break
        return container

    def run_one_instance(self, instance_id: str):
        """
        Run a single instance using the prepared experiment container.

        Args:
            instance_id: The ID of the instance to run.
        """
        instance: dict[str, str] | None = None
        for inst in self.dataset:  # pyright: ignore[reportUnknownVariableType]
            if inst["instance_id"] == instance_id:  # pyright: ignore
                instance = inst  # pyright: ignore
        if instance is None:
            print(f"Instance {instance_id} not found.")
            return

        container = self.prepare_experiment_container(instance)
        instance_dir = instance["instance_id"]
        problem_statement_path = instance_dir + "/problem_statement.txt"
        patch_file_path = instance_dir + f"/{instance['instance_id']}.patch"
        traj_path = instance_dir + f"/{instance['instance_id']}.json"
        command = f'source trae-agent/.venv/bin/activate && trae-cli run {problem_statement_path} --working-dir="/testbed/" --config-file trae_config_local.json --max-steps 200 --must-patch --patch-path {patch_file_path} --trajectory-file {traj_path}'
        new_command = f"/bin/bash -c '{command}'"

        try:
            return_code, output = docker_exec(container, new_command)
            if return_code is not None and return_code != 0:
                print("Docker exec error. Error message: {}".format(output))
        except Exception:
            print(f"{command} failed.")
            print(traceback.format_exc())

        container.stop()

    def run_all(self):
        """
        Run all instances in the dataset.
        """
        for instance in tqdm(self.dataset, desc="Running all instances"):  # pyright: ignore
            self.run_one_instance(instance["instance_id"])  # pyright: ignore

    def run_eval(self):
        """
        Run evaluation using the SWE-bench harness.
        """
        swebench_harness_path = Path(self.swebench_harness_path)
        swebench_python_path = "swebench_venv/bin/python"

        cmd = [
            swebench_python_path,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            f"princeton-nlp/{self.dataset_name}",
            "--predictions_path",
            (self.working_dir / "predictions.json").absolute().as_posix(),
            "--run_id",
            self.run_id,
            "--cache_level",
            "instance",
            "--instance_image_tag",
            "latest",
        ]

        process = subprocess.run(cmd, capture_output=True, cwd=swebench_harness_path.as_posix())
        print(process.stdout.decode())
        print(process.stderr.decode())

        result_filename = f"trae-agent.{self.run_id}.json"
        print(f"Evaluation completed and file saved to {result_filename}")

    def get_all_preds(self, instance_ids: list[str] | None = None):
        """
        Get all predictions for a list of instance IDs.

        Args:
            instance_ids: A list of instance IDs. If None, all instances in the dataset will be used.
        """
        preds: list[dict[str, str]] = []
        if not instance_ids:
            instance_ids = [instance["instance_id"] for instance in self.dataset]  # pyright: ignore
        for instance_id in instance_ids:
            patch_path = self.working_dir / instance_id / f"{instance_id}.patch"
            if not patch_path.exists():
                continue
            with open(patch_path, "r") as f:
                patch = f.read()
            preds.append(
                {
                    "instance_id": instance_id,
                    "model_name_or_path": "trae-agent",
                    "model_patch": patch,
                }
            )
        with open(self.working_dir / "predictions.json", "w") as f:
            json.dump(preds, f)


def main():
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--dataset", type=str, default="SWE-bench_Verified")
    argument_parser.add_argument("--working-dir", type=str, default="./trae-workspace")
    argument_parser.add_argument("--config-file", type=str, default="trae_config_local.json")
    argument_parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )
    argument_parser.add_argument(
        "--swebench-harness-path",
        type=str,
        default="",
        required=False,
        help="Only used for evaluation.",
    )
    argument_parser.add_argument("--docker-env-config", type=str, default="", required=False)
    argument_parser.add_argument(
        "--run-id",
        type=str,
        required=False,
        default="trae-agent",
        help="Run ID for SWE-bench evaluation.",
    )
    # expr: only generate patches
    # eval: only evaluation patches
    # e2e: both expr and eval
    argument_parser.add_argument(
        "--mode",
        type=str,
        choices=["e2e", "expr", "eval"],
        default="e2e",
        help="e2e: both expr and eval, expr: only generate patches, eval: only evaluation patches",
    )

    args = argument_parser.parse_args()
    evaluation = SWEBenchEvaluation(
        args.working_dir,
        args.config_file,
        args.dataset,
        args.docker_env_config,
        args.swebench_harness_path,
        args.run_id,
    )

    if args.mode == "e2e" or args.mode == "expr":
        evaluation.prepare_trae_agent()

        if args.instance_ids:
            print(f"Running instance {args.instance_ids}")
            for instance_id in tqdm(args.instance_ids, desc="Running instances"):
                evaluation.run_one_instance(instance_id)
        else:
            print("Running all instances")
            evaluation.run_all()

    if args.mode == "e2e" or args.mode == "eval":
        evaluation.get_all_preds(args.instance_ids)
        evaluation.run_eval()


if __name__ == "__main__":
    main()
