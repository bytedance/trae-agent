"""`server/Readme.md` must not describe a server the repository does not ship.

The page opens with "This folder contains the elements for hosting the Trae agent as an HTTP server
using FastAPI", while `server/` has held one file -- that README -- in every commit since it was added
by #249. A reader who believes the sentence looks for a module to run and finds none. The checks below
pin the page to two facts a reader can verify without starting anything: whether the folder contains a
Python module, and which commands the package actually installs. Both are read from the repository
itself, so the test needs no install, no network and no server.
"""

import re
import tomllib
import unittest
from pathlib import Path

NOT_IMPLEMENTED = re.compile(
    r"\bnot (?:yet )?implemented\b"
    r"|\bhas not been (?:implemented|built|started)\b"
    r"|\bis not (?:implemented|available|here)\b"
    r"|\bdoes not exist\b"
    r"|\bno code\b",
    re.IGNORECASE,
)

# A backticked hyphenated lowercase word is how this repository writes an installed command: `trae-cli`.
COMMAND_TOKEN = re.compile(r"`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`")

ONLY_ENTRY_POINT = re.compile(r"only (?:entry point|interface|command)", re.IGNORECASE)

SPECIFICATION_SECTIONS = (
    "## Expected Features of the HTTP Server",
    "## Additional Features Expected",
    "## Roadmap",
)


class ServerReadmeAccuracyTest(unittest.TestCase):
    _root: Path
    _readme: Path
    _text: str
    _scripts: frozenset[str]
    _modules: list[Path]

    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parent
        while not (root / "server" / "Readme.md").is_file() and root.parent != root:
            root = root.parent
        cls._root = root
        cls._readme = root / "server" / "Readme.md"
        cls._text = cls._readme.read_text(encoding="utf-8")
        with (root / "pyproject.toml").open("rb") as pyproject:
            cls._scripts = frozenset(tomllib.load(pyproject)["project"].get("scripts", {}))
        cls._modules = sorted((root / "server").rglob("*.py"))

    def test_a_folder_with_no_module_is_not_described_as_holding_one(self):
        """Either the folder ships the server, or the page says the server does not exist."""
        if self._modules:
            return
        if NOT_IMPLEMENTED.search(self._text) is not None:
            return
        self.fail(
            f"{self._readme} presents the HTTP server as present, but `server/` contains no Python "
            "module; the page has to say the server has not been implemented yet."
        )

    def test_the_page_only_names_commands_the_package_installs(self):
        named = frozenset(COMMAND_TOKEN.findall(self._text))
        unknown = sorted(named - self._scripts)
        if unknown:
            self.fail(
                f"{self._readme} tells the reader to run {unknown}, which pyproject.toml does not "
                f"declare under [project.scripts] (declared: {sorted(self._scripts)})."
            )

    def test_a_page_that_calls_one_entry_point_the_only_one_is_right(self):
        if ONLY_ENTRY_POINT.search(self._text) is None:
            return
        self.assertEqual(
            1,
            len(self._scripts),
            f"{self._readme} calls one entry point the only one, but pyproject.toml declares "
            f"{sorted(self._scripts)}.",
        )
        self.assertTrue(
            self._scripts.intersection(frozenset(COMMAND_TOKEN.findall(self._text))),
            f"{self._readme} promises an entry point without naming one of {sorted(self._scripts)}.",
        )

    def test_the_design_notes_survive_the_accuracy_fix(self):
        """The specification is the useful half of this page; correcting the header must not remove it."""
        missing = [section for section in SPECIFICATION_SECTIONS if section not in self._text]
        self.assertEqual([], missing, f"{self._readme} no longer carries {missing}.")


if __name__ == "__main__":
    unittest.main()
