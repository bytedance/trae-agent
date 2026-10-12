"""Offline evaluation regression checks at the Docker and harness boundaries."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import ImageNotFound

from evaluation import run_evaluation, utils


@pytest.mark.parametrize("benchmark", list(utils.BENCHMARK_CONFIG))
@pytest.mark.parametrize("selection", [None, ["org__repo-2"], "empty-dataset"])
def test_constructor_initializes_instance_selection(tmp_path, monkeypatch, benchmark, selection):
    monkeypatch.chdir(tmp_path)
    instances = [{"instance_id": f"org__repo-{n}"} for n in (1, 2)]
    if selection == "empty-dataset":
        instances = []
        selection = None
    config = utils.BENCHMARK_CONFIG[benchmark]
    monkeypatch.setattr(config, "load_dataset", lambda _: instances)
    docker = MagicMock()
    docker.images.get.side_effect = ImageNotFound("not cached")
    monkeypatch.setattr(run_evaluation, "from_env", lambda: docker)
    source_config = tmp_path / "trae_config.yaml"
    source_config.write_text("agents: {}\n", encoding="utf-8")
    evaluator = run_evaluation.BenchmarkEvaluation(
        benchmark,
        "workspace",
        str(source_config),
        dataset=config.valid_datasets[0],
        instance_ids=selection,
    )
    expected = selection if selection is not None else [i["instance_id"] for i in instances]
    assert evaluator.instance_ids == expected
    pulled = [call.args[0] for call in docker.images.pull.call_args_list]
    assert pulled == ["ubuntu:22.04", *(config.image_name(i) for i in expected)]
    assert (tmp_path / "workspace/trae_config.yaml").read_bytes() == source_config.read_bytes()
    assert evaluator.task_results_dir.is_dir()


@pytest.mark.parametrize("dataset_name", utils.BENCHMARK_CONFIG["Multi-SWE-bench"].valid_datasets)
@pytest.mark.parametrize("path_kind", ["relative-path", "relative-string", "absolute", "dot-dot"])
@pytest.mark.parametrize("row_count", [0, 1, 3])
def test_multi_paths_and_repeated_preparation(
    tmp_path, monkeypatch, dataset_name, path_kind, row_count
):
    root = tmp_path / "project with spaces \u4e2d\u6587"
    root.mkdir()
    (root / "evaluation").mkdir()
    monkeypatch.setattr(utils, "__file__", str(root / "evaluation/utils.py"))
    monkeypatch.chdir(root)
    instances = [
        {"instance_id": f"org__repo-{n}", "org": "org", "repo": "repo", "number": n}
        for n in range(row_count)
    ]
    dataset = root / f"{dataset_name.lower().replace('-', '_')}.jsonl"
    dataset.write_text(
        "\n" + "\n\n".join(json.dumps(i) for i in instances) + "\n", encoding="utf-8"
    )
    assert utils._load_jsonl_dataset(dataset_name) == instances
    results = root / "results/run with spaces"
    results.mkdir(parents=True)
    (root / "scratch").mkdir()
    paths = {
        "relative-path": Path("results/run with spaces"),
        "relative-string": "results/run with spaces",
        "absolute": results,
        "dot-dot": Path("scratch/../results/run with spaces"),
    }
    path = paths[path_kind]
    config = utils.BENCHMARK_CONFIG["Multi-SWE-bench"]
    # Repeated calls must replace, not append to, a previous predictions file.
    for count in (row_count, 0):
        predictions = [
            {"instance_id": i["instance_id"], "model_patch": "diff \u4e2d\u6587\n+line\n"}
            for i in instances[:count]
        ]
        (results / "predictions.json").write_text(json.dumps(predictions), encoding="utf-8")
        config.evaluate_harness_before(path, dataset_name, 3)
        command = config.evaluate_harness(dataset_name, path, "run with spaces", 3)
        config_path = Path(command[command.index("--config") + 1])
        assert config_path == results / "evaluate_config.json"
        generated = json.loads(config_path.read_text(encoding="utf-8"))
        assert generated["max_workers"] == 3
        assert Path(generated["dataset_files"][0]) == dataset
        assert Path(generated["patch_files"][0]) == results / "predictions.jsonl"
        rows = [
            json.loads(line)
            for line in Path(generated["patch_files"][0]).read_text(encoding="utf-8").splitlines()
        ]
        assert len(rows) == count
        assert [row["number"] for row in rows] == list(range(count))
        assert all(row["fix_patch"] == "diff \u4e2d\u6587\n+line\n" for row in rows)
        for key in ("output_dir", "workdir", "repo_dir", "log_dir"):
            assert Path(generated[key]).is_absolute()
            assert Path(generated[key]).is_dir()
    assert not (root / "evaluation/results").exists()


@pytest.mark.parametrize("dataset_name", utils.BENCHMARK_CONFIG["Multi-SWE-bench"].valid_datasets)
def test_run_eval_uses_config_in_real_child_process(tmp_path, monkeypatch, dataset_name):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evaluation").mkdir()
    monkeypatch.setattr(utils, "__file__", str(tmp_path / "evaluation/utils.py"))
    (tmp_path / f"{dataset_name.lower().replace('-', '_')}.jsonl").write_text(
        '{"instance_id":"org__repo-1","org":"org","repo":"repo","number":1}\n', encoding="utf-8"
    )
    results = Path("results/child-process")
    results.mkdir(parents=True)
    (results / "predictions.json").write_text(
        '[{"instance_id":"org__repo-1","model_patch":"patch"}]', encoding="utf-8"
    )
    harness = tmp_path / "harness with spaces"
    harness.mkdir()
    child = harness / "check_config.py"
    child.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "cfg = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "for key in ('patch_files', 'dataset_files'):\n"
        "    for value in cfg[key]:\n"
        "        p = Path(value)\n"
        "        assert p.is_absolute() and p.is_file(), value\n"
        "        assert json.loads(p.read_text(encoding='utf-8'))\n"
        "Path(cfg['output_dir'], 'final_report.json').write_text('{\"resolved\": 1}')\n",
        encoding="utf-8",
    )
    actual = utils.BENCHMARK_CONFIG["Multi-SWE-bench"]

    def local_harness(*args):
        command = actual.evaluate_harness(*args)
        return [sys.executable, str(child), command[command.index("--config") + 1]]

    evaluator = run_evaluation.BenchmarkEvaluation.__new__(run_evaluation.BenchmarkEvaluation)
    evaluator.config = replace(actual, evaluate_harness=local_harness)
    evaluator.task_results_dir = results
    evaluator.dataset_name = dataset_name
    evaluator.max_workers = 1
    evaluator.task_id = "child-process"
    evaluator.benchmark_harness_path = str(harness)
    # Real run_eval, real subprocess, real before/after hooks; only external harness substituted.
    evaluator.run_eval()
    assert json.loads((results / "results.json").read_text()) == {"resolved": 1}


@pytest.mark.parametrize("mode", ["expr", "eval", "e2e"])
@pytest.mark.parametrize("explicit_ids", [False, True])
def test_main_dispatches_mode_without_running_other_modes(monkeypatch, mode, explicit_ids):
    evaluator = MagicMock()
    factory = MagicMock(return_value=evaluator)
    monkeypatch.setattr(run_evaluation, "BenchmarkEvaluation", factory)
    argv = ["run_evaluation", "--mode", mode]
    if explicit_ids:
        argv.extend(["--instance_ids", "org__repo-1", "org__repo-2"])
    monkeypatch.setattr(sys, "argv", argv)
    run_evaluation.main()
    evaluator.prepare_trae_agent.assert_called_once()
    assert evaluator.run_eval.call_count == int(mode in ("eval", "e2e"))
    assert evaluator.get_all_preds.call_count == int(mode in ("eval", "e2e"))
    assert evaluator.run_all.call_count == int(not explicit_ids and mode in ("expr", "e2e"))
    assert evaluator.run_one_instance.call_count == (
        2 if explicit_ids and mode in ("expr", "e2e") else 0
    )
