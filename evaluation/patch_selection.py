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


class SWEBenchPatchSelection:
    def __init__(
        self,
        *,
        working_dir: str,
        trae_config_file_name: str,
        instances_path: str,
        candidate_file: str,
        docker_env_config: str = "",
        num_candidate: int,
        group_size: int,
        max_retry: int,
        max_turn: int,
        majority_voting: bool,
    ):
        """
        Initialize the SWEBenchPatchSelection class. The initialisation includes checking the existence of required Docker images and downloading missing images.

        Args:
            working_dir: The working directory.
            trae_config_file_name: The path to the Trae config file.
            dataset: The dataset to evaluate.
            candidate_file: The path to the candidate file.
            docker_env_config: The path to the docker environment config file.
            num_candidate: The number of candidate patches.
            group_size: The group size of candidate patches.
            max_retry: The maximum number of retries.
            max_turn: The maximum number of turns.
            majority_voting: Whether to use majority voting.
        """
        self.docker_client: DockerClient = from_env()
        self.image_status: dict[Any, Any] = {}
        self.working_dir = Path(working_dir)
        self.num_candidate = num_candidate
        self.group_size = group_size
        self.max_retry = max_retry
        self.max_turn = max_turn
        self.majority_voting = majority_voting

        if not Path(candidate_file).exists():
            raise FileNotFoundError(f"Candidate file {candidate_file} not found.")
        self.candidate_dict = {}
        with open(candidate_file, "r") as f:
            for line in f.readlines():
                candidate = json.loads(line.strip())
                if "regressions" not in candidate:
                    candidate["regressions"] = []
                    for _ in range(len(candidate["patches"])):
                        candidate["regressions"].append([])
                self.candidate_dict[candidate["instance_id"]] = candidate

        self.dataset = []
        with open(instances_path, "r") as f:
            for line in f.readlines():
                instance = json.loads(line.strip())
                self.dataset.append(instance)

        if docker_env_config != "":
            with open(docker_env_config, "r") as f:
                self.docker_env_config: dict[str, dict[str, str]] = json.load(f)
        else:
            self.docker_env_config = {}

        if not self.working_dir.exists():
            self.working_dir.mkdir(parents=True, exist_ok=True)

        self.trae_config_file_name = trae_config_file_name

        shutil.copyfile(self.trae_config_file_name, self.working_dir / "trae_config.yaml")
        shutil.copyfile(instances_path, self.working_dir / "instances.jsonl")
        shutil.copyfile(candidate_file, self.working_dir / "candidate.jsonl")

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

        repo_root_path = Path(__file__).parent.parent
        assert (repo_root_path / "trae_agent" / "__init__.py").is_file()

        container = self.docker_client.containers.run(
            image=image,
            command="bash",
            detach=True,
            tty=True,
            stdin_open=True,
            volumes={
                self.working_dir.absolute().as_posix(): {"bind": "/trae-workspace", "mode": "rw"},
                repo_root_path.absolute().as_posix(): {"bind": "/trae-src", "mode": "ro"},
            },
            environment=self.docker_env_config.get("preparation_env", None),  # pyright: ignore[reportUnknownMemberType]
        )

        commands = [
            "apt-get update",
            "apt-get install -y curl",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "rm -rf /trae-workspace/trae-agent && mkdir /trae-workspace/trae-agent",
            "cp -r -t /trae-workspace/trae-agent/ /trae-src/trae_agent /trae-src/.python-version /trae-src/pyproject.toml /trae-src/uv.lock /trae-src/README.md",
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
        command = f'source trae-agent/.venv/bin/activate && python3 trae_agent/patch_selection.py --instances_path {self.working_dir / "instances.jsonl"} --candidate_path {self.working_dir / "candidate.jsonl"} --result_path {instance_dir} --num_candidate {self.num_candidate} --group_size {self.group_size} --max_retry {self.max_retry} --max_turn {self.max_turn} --config_file {self.working_dir / "trae_config.yaml"} --instance_id {instance_id}'
        if self.majority_voting:
            command += " --majority_voting"
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


def main():
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--instances-path", type=str, required=True)
    argument_parser.add_argument("--candidate-file", type=str, required=True)
    argument_parser.add_argument("--working-dir", type=str, default="./trae-workspace")
    argument_parser.add_argument("--config-file", type=str, default="trae_config.yaml")
    argument_parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )
    argument_parser.add_argument("--docker-env-config", type=str, default="", required=False)
    argument_parser.add_argument("--num-candidate", type=int, default=10)
    argument_parser.add_argument("--group-size", type=int, default=10)
    argument_parser.add_argument("--max-retry", type=int, default=3)
    argument_parser.add_argument("--max-turn", type=int, default=50)
    argument_parser.add_argument("--majority-voting", action="store_true")

    args = argument_parser.parse_args()
    patch_selection = SWEBenchPatchSelection(
        working_dir=args.working_dir,
        trae_config_file_name=args.config_file,
        instances_path=args.instances_path,
        candidate_file=args.candidate_file,
        docker_env_config=args.docker_env_config,
        num_candidate=args.num_candidate,
        group_size=args.group_size,
        max_retry=args.max_retry,
        max_turn=args.max_turn,
        majority_voting=args.majority_voting,
    )

    patch_selection.prepare_trae_agent()

    if args.instance_ids:
        print(f"Running instance {args.instance_ids}")
        for instance_id in tqdm(args.instance_ids, desc="Running instances"):
            patch_selection.run_one_instance(instance_id)
    else:
        print("Running all instances")
        patch_selection.run_all()


if __name__ == "__main__":
    main()
