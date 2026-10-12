"""Check evaluation instructions without importing optional evaluation dependencies."""

import argparse
import ast
import re
import shlex
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / "evaluation"


class TestEvaluationDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (EVALUATION / "README.md").read_text(encoding="utf-8")
        runner = ast.parse((EVALUATION / "run_evaluation.py").read_text(encoding="utf-8"))
        main = next(
            node
            for node in runner.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        # Execute only parser construction, never imports or evaluation initialization.
        parser_nodes = [
            node
            for node in main.body
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "argument_parser" for t in node.targets)
            )
            or (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "add_argument"
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == "argument_parser"
            )
        ]
        namespace = {"argparse": argparse}
        exec(compile(ast.Module(body=parser_nodes, type_ignores=[]), "<parser>", "exec"), namespace)
        cls.parser = namespace["argument_parser"]
        cls.flags = {
            ast.literal_eval(node.value.args[0])
            for node in parser_nodes
            if isinstance(node, ast.Expr)
        }
        utils = ast.parse((EVALUATION / "utils.py").read_text(encoding="utf-8"))
        config = next(
            node.value
            for node in utils.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "BENCHMARK_CONFIG"
        )
        cls.datasets = {
            ast.literal_eval(key): next(
                ast.literal_eval(kw.value) for kw in value.keywords if kw.arg == "valid_datasets"
            )
            for key, value in zip(config.keys, config.values, strict=True)
        }
        cls.commands = []
        for block in re.findall(r"```bash\n(.*?)```", cls.readme, re.S):
            for line in block.replace("\\\n", " ").splitlines():
                tokens = shlex.split(line, comments=True)
                if tokens[:2] == ["uv", "run"]:
                    tokens = tokens[2:]
                if tokens and tokens[0] in {"python", "python3"}:
                    cls.commands.append(tokens)

    def test_examples_use_an_existing_package_module(self):
        self.assertTrue(self.commands, "No Python examples found")
        for command in self.commands:
            with self.subTest(command=command):
                self.assertEqual(command[1:3], ["-m", "evaluation.run_evaluation"])
                module = ROOT.joinpath(*command[2].split("."))
                self.assertTrue(module.with_suffix(".py").is_file())
                self.assertTrue((module.parent / "__init__.py").is_file())

    def test_examples_parse_and_use_matching_benchmarks_and_datasets(self):
        for command in self.commands:
            with self.subTest(command=command):
                self.assertEqual(command[1], "-m")
                args = self.parser.parse_args(command[3:])
                self.assertIn(args.dataset, self.datasets[args.benchmark])

    def test_parameter_list_matches_parser(self):
        section = self.readme.split("**Parameters:**", 1)[1].split("## How It Works", 1)[0]
        documented = set(re.findall(r"^- `(--[\w-]+)`", section, re.M))
        self.assertEqual(documented, self.flags)

    def test_documented_modes_match_parser(self):
        choices = next(action.choices for action in self.parser._actions if action.dest == "mode")
        section = self.readme.split("### Evaluation Modes", 1)[1].split("```", 1)[0]
        modes = re.findall(r"^\d+\. \*\*`([^`]+)`\*\*", section, re.M)
        with self.subTest(location="Evaluation Modes"):
            self.assertCountEqual(modes, choices)

        parameters = self.readme.split("**Parameters:**", 1)[1].split("## How It Works", 1)[0]
        description = re.search(r"^- `--mode`:(.*)$", parameters, re.M)
        self.assertIsNotNone(description, "Missing --mode parameter description")
        with self.subTest(location="Parameters"):
            self.assertCountEqual(re.findall(r"`([^`]+)`", description[1]), choices)

    def test_referenced_scripts_exist(self):
        # Check prose, links, and shell blocks, including commands without Python.
        scripts = set(re.findall(r"(?<![\w./-])([\w./-]+\.(?:py|sh))(?![\w.-])", self.readme))
        self.assertTrue(scripts, "No script references found")
        for script in sorted(scripts):
            with self.subTest(script=script):
                # Paths are root-relative; bare names can refer to setup's evaluation cwd.
                self.assertTrue(
                    (ROOT / script).is_file() or (EVALUATION / script).is_file(),
                    f"Documented script does not exist: {script}",
                )

    def test_benchmark_and_dataset_lists_match_config(self):
        section = self.readme.split("### Available Benchmarks and Datasets", 1)[1]
        section = section.split("### Evaluation Modes", 1)[0]
        documented = {}
        benchmark = None
        for line in section.splitlines():
            heading = re.match(r"^\*\*([^*]+)\*\*", line)
            dataset = re.match(r"^- \*\*([^*]+)\*\*", line)
            if heading:
                benchmark = heading[1]
                documented[benchmark] = []
            elif dataset:
                self.assertIsNotNone(benchmark)
                documented[benchmark].append(dataset[1])
        self.assertEqual(
            {k: set(v) for k, v in documented.items()},
            {k: set(v) for k, v in self.datasets.items()},
        )

    def test_setup_and_evaluation_share_harness_location(self):
        # A subshell confines setup's working-directory change to that command.
        setup = re.search(r"\(cd ([\w./-]+) && bash ([\w./-]+) (\w+)\)", self.readme)
        self.assertIsNotNone(setup, "Set up the harness in a subshell from the repository root")
        setup_dir = ROOT / setup[1]
        source = (setup_dir / setup[2]).read_text(encoding="utf-8")
        clones = dict(
            re.findall(r"(\w+)\)\s+.*?git clone https://[^\s]+/([^/\s]+)\.git", source, re.S)
        )
        self.assertIn(setup[3], clones)
        for command in self.commands:
            with self.subTest(command=command):
                self.assertEqual(command[1], "-m")
                args = self.parser.parse_args(command[3:])
                if args.mode in {"eval", "e2e"}:
                    self.assertTrue(args.benchmark_harness_path)
                    key = args.benchmark.lower().replace("-", "_")
                    self.assertEqual(
                        (ROOT / args.benchmark_harness_path).resolve(),
                        (setup_dir / clones[key]).resolve(),
                    )


if __name__ == "__main__":
    unittest.main()
