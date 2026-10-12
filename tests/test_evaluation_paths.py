"""Exercise local Multi-SWE-bench paths without Docker, downloads, or model calls."""

import json
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

from evaluation import utils


class TestMultiSweBenchPaths(unittest.TestCase):
    def test_harness_reads_generated_files_and_copies_report(self):
        for absolute_results in (False, True):
            with (
                self.subTest(absolute_results=absolute_results),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp).resolve()
                source_dir = root / "evaluation"
                source_dir.mkdir()
                dataset = root / "multi_swe_bench_flash.jsonl"
                instance = {"instance_id": "org__repo-1", "org": "org", "repo": "repo", "number": 1}
                dataset.write_text(json.dumps(instance) + "\n", encoding="utf-8")
                task_id = "test-run"
                results = root / "results" / task_id
                results.mkdir(parents=True)
                predictions = [{"instance_id": instance["instance_id"], "model_patch": "patch"}]
                (results / "predictions.json").write_text(json.dumps(predictions), encoding="utf-8")
                task_path = results if absolute_results else Path("results") / task_id
                config = utils.BENCHMARK_CONFIG["Multi-SWE-bench"]
                with chdir(root), patch.object(utils, "__file__", str(source_dir / "utils.py")):
                    self.assertEqual(config.load_dataset("Multi-SWE-bench-flash"), [instance])
                    config.evaluate_harness_before(task_path, "Multi-SWE-bench-flash", 2)
                    command = config.evaluate_harness(
                        "Multi-SWE-bench-flash", task_path, task_id, 2
                    )
                    config_path = Path(command[command.index("--config") + 1])
                    self.assertTrue(config_path.is_absolute())
                    self.assertEqual(config_path, results / "evaluate_config.json")
                    # The harness runs in a different directory: its inputs must still resolve.
                    harness = root / "harness"
                    harness.mkdir()
                    with chdir(harness):
                        generated = json.loads(config_path.read_text(encoding="utf-8"))
                        self.assertEqual(Path(generated["dataset_files"][0]), dataset)
                        patch_path = Path(generated["patch_files"][0])
                        self.assertEqual(patch_path, results / "predictions.jsonl")
                        self.assertEqual(
                            json.loads(patch_path.read_text(encoding="utf-8")),
                            {"org": "org", "repo": "repo", "number": 1, "fix_patch": "patch"},
                        )
                        self.assertEqual(json.loads(dataset.read_text(encoding="utf-8")), instance)
                        for key in ("workdir", "repo_dir", "log_dir", "output_dir"):
                            self.assertTrue(Path(generated[key]).is_absolute())
                            self.assertTrue(Path(generated[key]).is_dir())
                        report = {"resolved": 1}
                        (Path(generated["output_dir"]) / "final_report.json").write_text(
                            json.dumps(report), encoding="utf-8"
                        )
                    config.evaluate_harness_after(str(harness), task_id)
                    self.assertEqual(json.loads((results / "results.json").read_text()), report)
                    self.assertFalse((source_dir / "results").exists())


if __name__ == "__main__":
    unittest.main()
