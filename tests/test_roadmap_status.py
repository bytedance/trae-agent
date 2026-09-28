"""`docs/roadmap.md` must agree with what the repository actually contains.

The roadmap lists "MCP Integration: Implement Model Context Protocol" as planned work, while
`mcp==1.12.2` is a declared dependency (`pyproject.toml:22`), `trae_agent/tools/mcp_tool.py` and
`trae_agent/utils/mcp_client.py` implement it, `README.md` documents the `mcp_servers` configuration, and
fifteen tests for it pass without network access. `README.md:13` points contributors at this file, so a
reader cannot tell finished work from a request. The checks below compare each capability the repository
can be tested for against how the page marks it, in both directions: shipped-but-listed-as-planned (the
bug) and planned-but-marked-shipped (the bug a future edit would introduce). Everything is read from the
repository with `tomllib` and plain file access, so the test needs no install and no network.
"""

import re
import tomllib
import unittest
from pathlib import Path

SHIPPED_MARKER = "[shipped]"
MARKER = re.compile(re.escape(SHIPPED_MARKER), re.IGNORECASE)
BULLET = re.compile(r"^- \*\*(?P<name>[^*]+)\*\*(?P<rest>.*)$")
REPO_PATH = re.compile(r"`([\w./-]*/[\w./-]*)`")
DEPENDENCY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _dependency_names(pyproject: Path) -> frozenset[str]:
    with pyproject.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    declared = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)
    names: set[str] = set()
    for entry in declared:
        found = DEPENDENCY_NAME.match(entry.strip())
        if found is not None:
            names.add(found.group(0).lower().replace("_", "-"))
    return frozenset(names)


def _package_source(root: Path) -> str:
    chunks = []
    for source in sorted((root / "trae_agent").rglob("*.py")):
        chunks.append(source.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _mcp_is_shipped(root: Path, deps: frozenset[str]) -> bool:
    return "mcp" in deps and (root / "trae_agent" / "tools" / "mcp_tool.py").is_file()


def _jupyter_is_shipped(root: Path, deps: frozenset[str]) -> bool:
    # A notebook would have to be recognised by name somewhere in the package to be supported.
    return "ipynb" in _package_source(root)


def _mlops_is_shipped(root: Path, deps: frozenset[str]) -> bool:
    return not {"wandb", "mlflow"}.isdisjoint(deps)


CAPABILITIES = (
    ("MCP Integration", _mcp_is_shipped),
    ("Structured File Support", _jupyter_is_shipped),
    ("MLOps Integration", _mlops_is_shipped),
)


class RoadmapStatusTest(unittest.TestCase):
    _root: Path
    _roadmap: Path
    _text: str
    _deps: frozenset[str]

    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parent
        while not (root / "docs" / "roadmap.md").is_file() and root.parent != root:
            root = root.parent
        cls._root = root
        cls._roadmap = root / "docs" / "roadmap.md"
        cls._text = cls._roadmap.read_text(encoding="utf-8")
        cls._deps = _dependency_names(root / "pyproject.toml")

    def _bullets(self) -> dict[str, str]:
        bullets: dict[str, str] = {}
        for line in self._text.splitlines():
            found = BULLET.match(line)
            if found is not None:
                bullets[found.group("name").strip()] = line
        return bullets

    def test_each_capability_is_marked_the_way_the_repository_has_it(self):
        bullets = self._bullets()
        wrong = []
        for name, shipped_of in CAPABILITIES:
            line = bullets.get(name)
            if line is None:
                wrong.append(f"{name}: docs/roadmap.md no longer carries this bullet")
                continue
            marked = MARKER.search(line) is not None
            if marked != shipped_of(self._root, self._deps):
                wrong.append(
                    f"{name}: page marks it {'shipped' if marked else 'planned'}, "
                    f"the repository says {'shipped' if not marked else 'planned'}"
                )
        if wrong:
            self.fail("; ".join(wrong))

    def test_a_marker_the_page_never_defines_cannot_be_relied_on(self):
        if MARKER.search(self._text) is None:
            return
        self.assertIn(
            SHIPPED_MARKER,
            self._text.split("## SDK Development")[0],
            f"{self._roadmap} uses {SHIPPED_MARKER} in its bullets without defining it above "
            "the first section.",
        )

    def test_every_repository_path_the_roadmap_cites_exists(self):
        cited = set(REPO_PATH.findall(self._text))
        missing = sorted(token for token in cited if not (self._root / token).exists())
        if missing:
            self.fail(
                f"{self._roadmap} cites {missing}, which is not in the repository at {self._root}."
            )

    def test_the_shipped_mcp_integration_is_not_described_as_something_to_build(self):
        """The sentence this issue is about, pinned directly."""
        if not _mcp_is_shipped(self._root, self._deps):
            self.skipTest("mcp_tool.py is gone from the repository; the roadmap needs a rethink")
        for line in self._text.splitlines():
            if MARKER.search(line) is not None:
                continue
            if re.search(
                r"\bimplement\w*\b[^\n]*\b(MCP|Model Context Protocol)\b", line, re.IGNORECASE
            ):
                self.fail(f"{self._roadmap} still asks a reader to implement MCP support: {line!r}")


if __name__ == "__main__":
    unittest.main()
