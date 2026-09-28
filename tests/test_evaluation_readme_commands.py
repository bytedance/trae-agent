"""Keep evaluation/README.md runnable against the two scripts it documents.

The page is the only entry point to the SWE-bench evaluation -- README.md never mentions evaluation -- and
on main all seven of its command lines fail: six run a package module as a script, and one names a file
that is not in the repository. These cases read the page, `evaluation/run_evaluation.py`,
`evaluation/setup.sh` and the `BENCHMARK_CONFIG` literal in `evaluation/utils.py` as text, so they need no
Docker, no install and no network.
"""

import re
import unittest
from pathlib import Path

GUIDE = Path("evaluation") / "README.md"
SCRIPT = Path("evaluation") / "run_evaluation.py"
SETUP = Path("evaluation") / "setup.sh"
CONFIG = Path("evaluation") / "utils.py"

# `python run_evaluation.py ...` / `python ./some/dir/script.py ...`
PATH_INVOCATION = re.compile(r"\bpython[3]?\s+(?P<target>(?:\S+/)?\w+\.py)")
MODULE_INVOCATION = re.compile(r"\bpython[3]?\s+-m\s+evaluation\.run_evaluation\b")
RUNS_EVALUATION = re.compile(
    r"\bpython[3]?\s+(?:-m\s+evaluation\.run_evaluation|(?:\S+/)?run_evaluation\.py)\b"
)
RELATIVE_IMPORT = re.compile(r"^(?:from|import)\s*\.", re.MULTILINE)
# Any file the page names, in prose or in a command.
NAMED_SCRIPT = re.compile(r"\b[\w./-]+\.(?:py|sh)\b")
HARNESS_PATH = re.compile(r"--benchmark-harness-path\s+(?P<path>\S+)")
GIT_CLONE = re.compile(r"git clone\s+(?P<url>\S+)")
BASH_BLOCK = re.compile(r"^```bash\n(?P<body>.*?)^```", re.MULTILINE | re.DOTALL)
ADD_ARGUMENT = re.compile(r'add_argument\(\s*"(?P<option>-{1,2}[A-Za-z0-9_-]+)"')
MODE_CHOICES = re.compile(r'add_argument\(\s*"--mode".*?choices=\[(?P<choices>[^\]]*)\]', re.DOTALL)
PARAMETERS_ENTRY = re.compile(r"^- `(?P<option>--[A-Za-z_-]+)`", re.MULTILINE)
FLAG_IN_COMMAND = re.compile(r"(?P<option>--[A-Za-z_][A-Za-z_-]*)")
# The BENCHMARK_CONFIG literal, field by field: `valid_datasets` is the first entry of each benchmark.
BENCHMARK_ENTRY = re.compile(r'^ {4}"(?P<name>[^"]+)": BenchmarkConfig\($', re.MULTILINE)
VALID_DATASETS = re.compile(r"^ {8}valid_datasets=\[(?P<items>[^\]]*)\],$", re.MULTILINE)
# The page's own inventory: `**SWE-bench**:` headings, `- **SWE-bench_Verified**` datasets under them.
PAGE_BENCHMARK = re.compile(r"^\*\*(?P<name>[^*]+)\*\*:?\s*$", re.MULTILINE)
PAGE_DATASET = re.compile(r"^- \*\*(?P<name>[^*]+)\*\*", re.MULTILINE)


def _bash_bodies(page: str) -> str:
    return "\n".join(BASH_BLOCK.findall(page))


def _evaluation_commands(page: str) -> list[str]:
    """The command lines that run the evaluation script, one string per command, continuations joined."""
    commands: list[str] = []
    current: list[str] = []
    for line in _bash_bodies(page).splitlines():
        if current or RUNS_EVALUATION.search(line):
            current.append(line)
            if not line.rstrip().endswith("\\"):
                commands.append(" ".join(current))
                current = []
    return commands


def _options(source: str) -> set[str]:
    return {match.group("option") for match in ADD_ARGUMENT.finditer(source)}


def _datasets(items: str) -> set[str]:
    return {value.strip().strip("\"'") for value in items.split(",") if value.strip()}


def _config_benchmarks(source: str) -> dict[str, set[str]]:
    """The benchmarks BENCHMARK_CONFIG defines and the datasets each one accepts, read in literal order."""
    entries = list(BENCHMARK_ENTRY.finditer(source))
    lists = list(VALID_DATASETS.finditer(source))
    if len(entries) != len(lists):
        return {}
    return {
        entry.group("name"): _datasets(datasets.group("items"))
        for entry, datasets in zip(entries, lists, strict=True)
    }


def _page_benchmarks(section: str) -> dict[str, set[str]]:
    """The page's 'Available Benchmarks and Datasets' list, grouped by the heading each entry sits under."""
    headings = list(PAGE_BENCHMARK.finditer(section))
    listed: dict[str, set[str]] = {}
    for position, heading in enumerate(headings):
        start = heading.end()
        end = headings[position + 1].start() if position + 1 < len(headings) else len(section)
        listed[heading.group("name")] = set(PAGE_DATASET.findall(section[start:end]))
    return listed


class EvaluationReadmeTest(unittest.TestCase):
    page: str
    script: str
    setup: str
    utils: str
    root: Path

    @classmethod
    def setUpClass(cls) -> None:
        directory = Path(__file__).resolve().parent
        while not (directory / GUIDE).is_file():
            if directory.parent == directory:
                raise AssertionError(f"{GUIDE} not found above {Path(__file__).resolve()}")
            directory = directory.parent
        cls.root = directory
        cls.page = (directory / GUIDE).read_text(encoding="utf-8")
        cls.script = (directory / SCRIPT).read_text(encoding="utf-8")
        cls.setup = (directory / SETUP).read_text(encoding="utf-8")
        cls.utils = (directory / CONFIG).read_text(encoding="utf-8")

    def test_the_page_never_runs_a_package_module_as_a_script(self) -> None:
        """`python run_evaluation.py` dies on its own second line, and the traceback blames nothing here."""
        offenders: list[str] = []
        for match in PATH_INVOCATION.finditer(_bash_bodies(self.page)):
            target = match.group("target")
            for candidate in (self.root / target, self.root / "evaluation" / target):
                if candidate.is_file() and RELATIVE_IMPORT.search(
                    candidate.read_text(encoding="utf-8")
                ):
                    offenders.append(target)
                    break
        self.assertEqual(
            offenders,
            [],
            "the page invokes these files as scripts, but they are modules of the `evaluation` package and"
            " start with a relative import, so Python refuses to run them this way:"
            f" {sorted(set(offenders))}. Use `python -m evaluation.run_evaluation` from the repository root.",
        )
        self.assertIsNotNone(
            MODULE_INVOCATION.search(_bash_bodies(self.page)),
            "the page no longer shows any `python -m evaluation.run_evaluation` command, so it documents no"
            " way to start the evaluation at all",
        )

    def test_every_script_the_page_names_exists(self) -> None:
        """A reader cannot run, open or patch a file this page invented."""
        missing: list[str] = []
        for name in sorted(set(NAMED_SCRIPT.findall(self.page))):
            candidates = [self.root / name, self.root / "evaluation" / name]
            if not any(candidate.is_file() for candidate in candidates):
                missing.append(name)
        self.assertEqual(
            missing,
            [],
            f"evaluation/README.md names these scripts, which are not in the repository: {missing}",
        )

    def test_harness_paths_match_where_setup_sh_clones(self) -> None:
        """setup.sh clones into its own directory; the reader runs the evaluation from the repository root."""
        clones = {
            url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
            for url in GIT_CLONE.findall(self.setup)
        }
        self.assertTrue(
            clones, "evaluation/setup.sh no longer clones any harness, so this case is stale"
        )
        shown = sorted({match.group("path") for match in HARNESS_PATH.finditer(self.page)})
        self.assertTrue(
            shown, "evaluation/README.md no longer shows a --benchmark-harness-path value"
        )
        wrong = [
            path
            for path in shown
            if path != f"./evaluation/{Path(path).name}" or Path(path).name not in clones
        ]
        self.assertEqual(
            wrong,
            [],
            "these --benchmark-harness-path values cannot resolve from the repository root, because"
            f" setup.sh clones each harness into evaluation/: {wrong}."
            f" Expected ./evaluation/ followed by one of {sorted(clones)}.",
        )

    def test_every_option_the_script_defines_is_documented(self) -> None:
        """The Parameters list is what a reader trusts to be complete."""
        block = self.page.split("**Parameters:**", 1)
        self.assertEqual(
            len(block), 2, "evaluation/README.md no longer has a '**Parameters:**' list"
        )
        documented = set(PARAMETERS_ENTRY.findall(block[1].split("\n## ", 1)[0]))
        undocumented = sorted(_options(self.script) - documented)
        self.assertEqual(
            undocumented,
            [],
            "evaluation/run_evaluation.py accepts these options that the page's Parameters list does not"
            f" mention: {undocumented}",
        )

    def test_every_flag_the_page_shows_is_one_the_script_accepts(self) -> None:
        """The other direction: a flag the script would reject is worse than a missing one."""
        shown: set[str] = set(PARAMETERS_ENTRY.findall(self.page))
        for command in _evaluation_commands(self.page):
            shown |= set(FLAG_IN_COMMAND.findall(command))
        invented = sorted(shown - _options(self.script))
        self.assertEqual(
            invented,
            [],
            "evaluation/README.md passes these flags to run_evaluation.py, which defines no such option,"
            f" so argparse would exit with 'unrecognized arguments': {invented}",
        )

    def test_documented_modes_are_the_modes_the_script_accepts(self) -> None:
        """A mode the parser has no branch for reads as a free choice."""
        match = MODE_CHOICES.search(self.script)
        self.assertIsNotNone(match, "run_evaluation.py no longer declares choices= for --mode")
        assert match is not None
        accepted = {value.strip().strip("\"'") for value in match.group("choices").split(",")}
        parameters = self.page.split("**Parameters:**", 1)[1].split("\n## ", 1)[0]
        line = [entry for entry in PARAMETERS_ENTRY.findall(parameters) if entry == "--mode"]
        self.assertTrue(line, "the Parameters list no longer documents --mode")
        described = set(
            re.findall(r"`(\w+)`", parameters.split("- `--mode`", 1)[1].split("\n", 1)[0])
        )
        self.assertEqual(
            described,
            accepted,
            "the page and the parser disagree about which --mode values exist:"
            f" page={sorted(described)} script={sorted(accepted)}",
        )

    def test_benchmarks_and_datasets_on_the_page_are_the_ones_the_code_accepts(self) -> None:
        """A name only the page carries raises at runtime; a name only the code carries is one no reader runs."""
        parts = self.page.split("### Available Benchmarks and Datasets", 1)
        self.assertEqual(
            len(parts),
            2,
            "evaluation/README.md no longer has an 'Available Benchmarks and Datasets' section",
        )
        defined = _config_benchmarks(self.utils)
        self.assertTrue(
            defined,
            "this case can no longer read BENCHMARK_CONFIG out of evaluation/utils.py, so it proves nothing",
        )
        listed = _page_benchmarks(parts[1].split("\n### ", 1)[0])
        self.assertTrue(
            listed,
            "the page's 'Available Benchmarks and Datasets' section lists no benchmark, so it proves nothing",
        )
        self.assertTrue(
            all(datasets for datasets in defined.values()) and all(listed.values()),
            "a benchmark was read with no datasets under it, which means the reading is wrong",
        )

        omitted = sorted(set(defined) - set(listed))
        invented = sorted(set(listed) - set(defined))
        disagreeing = [
            f"{name}: page_only={sorted(listed[name] - defined[name])}"
            f" code_only={sorted(defined[name] - listed[name])}"
            for name in sorted(set(defined) & set(listed))
            if defined[name] != listed[name]
        ]
        self.assertEqual(
            [omitted, invented, disagreeing],
            [[], [], []],
            "evaluation/README.md and BENCHMARK_CONFIG (evaluation/utils.py:181) disagree about what can be"
            " run; --benchmark is asserted against that table at evaluation/run_evaluation.py:55 and"
            f" --dataset at :58. Benchmarks the page omits={omitted}, benchmarks it invents={invented},"
            f" datasets that disagree per benchmark={disagreeing}",
        )


if __name__ == "__main__":
    unittest.main()
