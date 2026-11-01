# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

run_evaluation = pytest.importorskip(
    "evaluation.run_evaluation", reason="Evaluation dependencies are required"
)


@pytest.fixture
def evaluator(tmp_path):
    evaluator = run_evaluation.BenchmarkEvaluation.__new__(run_evaluation.BenchmarkEvaluation)
    evaluator.config = MagicMock()
    evaluator.task_results_dir = Path("results/test-run")
    evaluator.dataset_name = "SWE-bench_Verified"
    evaluator.task_id = "test-run"
    evaluator.max_workers = 1
    evaluator.benchmark_harness_path = str(tmp_path)
    return evaluator


@pytest.mark.parametrize("exit_code", [1, 7])
def test_run_eval_stops_after_harness_failure(evaluator, capsys, exit_code):
    evaluator.config.evaluate_harness.return_value = [
        sys.executable,
        "-c",
        "import sys; print('harness output'); print('harness error', file=sys.stderr); "
        f"sys.exit({exit_code})",
    ]

    with pytest.raises(subprocess.CalledProcessError) as error:
        evaluator.run_eval()

    assert error.value.returncode == exit_code
    output = capsys.readouterr().out
    assert "harness output" in output
    assert "harness error" in output
    assert "Evaluation completed" not in output
    evaluator.config.evaluate_harness_after.assert_not_called()


def test_run_eval_collects_results_after_harness_success(evaluator, capsys):
    evaluator.config.evaluate_harness.return_value = [
        sys.executable,
        "-c",
        "print('harness output')",
    ]

    evaluator.run_eval()

    output = capsys.readouterr().out
    assert "harness output" in output
    assert "Evaluation completed" in output
    evaluator.config.evaluate_harness_before.assert_called_once_with(
        evaluator.task_results_dir, evaluator.dataset_name, evaluator.max_workers
    )
    evaluator.config.evaluate_harness_after.assert_called_once_with(
        evaluator.benchmark_harness_path, evaluator.task_id
    )
