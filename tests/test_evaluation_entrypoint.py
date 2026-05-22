# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import runpy
import sys
import types
from pathlib import Path
from unittest.mock import patch


def test_run_evaluation_supports_direct_script_execution():
    docker_module = types.ModuleType("docker")
    docker_module.DockerClient = type("DockerClient", (), {})
    docker_module.from_env = lambda: None

    docker_errors = types.ModuleType("docker.errors")
    docker_errors.ImageNotFound = type("ImageNotFound", (Exception,), {})

    docker_models = types.ModuleType("docker.models")
    docker_containers = types.ModuleType("docker.models.containers")
    docker_containers.Container = type("Container", (), {})
    docker_containers.ExecResult = tuple

    datasets_module = types.ModuleType("datasets")
    datasets_module.load_dataset = lambda *args, **kwargs: []

    tqdm_module = types.ModuleType("tqdm")
    tqdm_module.tqdm = lambda iterable, **kwargs: iterable

    optional_modules = {
        "datasets": datasets_module,
        "docker": docker_module,
        "docker.errors": docker_errors,
        "docker.models": docker_models,
        "docker.models.containers": docker_containers,
        "tqdm": tqdm_module,
    }

    script_path = Path(__file__).resolve().parents[1] / "evaluation" / "run_evaluation.py"
    with patch.dict(sys.modules, optional_modules):
        namespace = runpy.run_path(str(script_path), run_name="run_evaluation_script")

    assert "BenchmarkEvaluation" in namespace
