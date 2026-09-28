# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""The documented setup has to be one an outside contributor can actually finish.

`CONTRIBUTING.md` is the page a first-time contributor is pointed at, and two of its instructions
were not executable. Step 2 was captioned "Clone your fork" while cloning
`https://github.com/bytedance/trae-agent.git` -- the upstream repository -- so the clone's only
remote, `origin`, was a repository the contributor cannot write to (`GET /repos/bytedance/trae-agent`
answers `permissions.push = false` for a non-member account, measured 2026-09-28), and step 4 of the
Development Process then told that contributor to run `git push origin <branch>` against it. The same
section tells the reader to run `make install-dev`, whose recipe is `uv venv` and `uv sync
--all-extras`, without naming `uv` anywhere in the file; `README.md` does list it, so the omission
was in the contribution page only.

These cases read `CONTRIBUTING.md` and the `Makefile` instead of running anything, so they need no
network access, no credentials and no container. They fail on the shape of the instructions, which is
where the drift happens, and they keep failing it from either file: renaming a target, dropping a
prerequisite or restoring the upstream clone URL breaks a test rather than a newcomer.
"""

import re
import unittest
from pathlib import Path

# The repository pull requests are opened against; `origin` must never be this one.
UPSTREAM = "bytedance/trae-agent"

# `make <target>` as the document tells the reader to run it.
MAKE_CALL = re.compile(r"\bmake\s+([A-Za-z0-9_.-]+)")

# A fenced block, whatever language tag it carries.
FENCED_BLOCK = re.compile(r"```[a-zA-Z]*\r?\n(.*?)```", re.DOTALL)

# `VAR=value` prefixes on a recipe line: they set the environment, they do not name a program.
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# A `target: prerequisites` line. Lines starting with `.` (`.PHONY`) are not real targets.
TARGET_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*):(.*)$")


def _word(text: str, needle: str) -> bool:
    """Whether `needle` occurs in `text` as a whole word, ignoring case."""
    boundary = r"[^A-Za-z0-9]"
    found = re.search(rf"(^|{boundary}){re.escape(needle)}({boundary}|$)", text, re.IGNORECASE)
    return found is not None


class ContributingSetupTest(unittest.TestCase):
    _root: Path
    _doc: str
    _make: str
    _blocks: list[str]
    _commands: list[str]
    _targets: dict[str, tuple[list[str], list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "CONTRIBUTING.md").is_file() and (parent / "Makefile").is_file():
                cls._root = parent
                break
        else:  # pragma: no cover - a source distribution without the build files
            raise unittest.SkipTest(f"no CONTRIBUTING.md + Makefile above {here}")
        cls._doc = (cls._root / "CONTRIBUTING.md").read_text(encoding="utf-8")
        cls._make = (cls._root / "Makefile").read_text(encoding="utf-8")
        cls._blocks = FENCED_BLOCK.findall(cls._doc)
        cls._commands = [
            line.strip() for block in cls._blocks for line in block.splitlines() if line.strip()
        ]
        cls._targets = cls._make_targets(cls._make)

    @staticmethod
    def _make_targets(text: str) -> dict[str, tuple[list[str], list[str]]]:
        """Map each Makefile target to its prerequisites and its recipe lines."""
        found: dict[str, tuple[list[str], list[str]]] = {}
        current: str | None = None
        for line in text.splitlines():
            definition = TARGET_LINE.match(line)
            if definition and not line.startswith(("\t", " ")):
                current = definition.group(1)
                found[current] = (definition.group(2).split(), [])
                continue
            if current is not None and line.startswith("\t"):
                prerequisites, recipe = found[current]
                found[current] = (prerequisites, recipe + [line.strip()])
        return found

    def _programs_of(self, target: str, seen: set[str] | None = None) -> set[str]:
        """The external programs a target's recipe runs, following its prerequisites."""
        visited = seen or set()
        if target in visited or target not in self._targets:
            return set()
        visited.add(target)
        prerequisites, recipe = self._targets[target]
        programs: set[str] = set()
        for dependency in prerequisites:
            programs |= self._programs_of(dependency, visited)
        for line in recipe:
            tokens = line.lstrip("@-").split()
            while tokens and ENV_ASSIGNMENT.match(tokens[0]):
                tokens = tokens[1:]
            if tokens:
                programs.add(tokens[0])
        return programs

    def test_the_document_contains_commands_to_check(self) -> None:
        """A vacuously empty extraction must not pass as a green run."""
        self.assertGreaterEqual(len(self._blocks), 3, self._blocks)
        self.assertGreaterEqual(len(self._commands), 4, self._commands)
        self.assertGreaterEqual(len(MAKE_CALL.findall(self._doc)), 2, MAKE_CALL.findall(self._doc))
        self.assertIn("install-dev", self._targets, sorted(self._targets))

    def test_the_clone_step_clones_a_fork_not_the_upstream_repository(self) -> None:
        clones = [command for command in self._commands if command.startswith("git clone")]
        self.assertEqual(len(clones), 1, clones)
        url = re.search(r"github\.com/([^\s/]+)/([^\s/]+)", clones[0])
        if url is None:
            self.fail(f"the clone step names no GitHub repository: {clones[0]}")
        owner, name = url.groups()
        self.assertTrue(name.rstrip("/") in ("trae-agent", "trae-agent.git"), clones[0])
        self.assertNotEqual(
            f"{owner}/{name.removesuffix('.git')}",
            UPSTREAM,
            f"`origin` would be the repository the contributor cannot push to: {clones[0]}",
        )

    def test_the_upstream_repository_is_configured_as_a_remote(self) -> None:
        additions = [c for c in self._commands if re.match(r"git remote add \S+", c)]
        self.assertTrue(
            any(UPSTREAM in c for c in additions),
            f"no `git remote add` names {UPSTREAM}: {additions}",
        )

    def test_every_remote_the_document_pushes_to_is_one_it_established(self) -> None:
        pushes = re.findall(r"\bgit push\s+(\S+)", "\n".join(self._commands))
        self.assertGreaterEqual(len(pushes), 1, pushes)
        established: set[str] = set()
        if any(command.startswith("git clone") for command in self._commands):
            established.add("origin")
        for command in self._commands:
            match = re.match(r"git remote add (\S+)", command)
            if match:
                established.add(match.group(1))
        for remote in pushes:
            self.assertIn(remote, established, f"`git push {remote}` names a remote nobody added")

    def test_the_document_shows_how_to_stay_current_with_upstream(self) -> None:
        commands = "\n".join(self._commands)
        self.assertIn("git fetch upstream", commands, self._commands)

    def test_every_make_target_the_document_names_exists(self) -> None:
        cited = MAKE_CALL.findall(self._doc)
        self.assertGreaterEqual(len(cited), 2, cited)
        for target in cited:
            self.assertIn(target, self._targets, f"`make {target}` is not a Makefile target")

    def test_the_document_names_the_programs_its_make_targets_execute(self) -> None:
        """`uv` bootstraps the environment, so nothing documented can install it for the reader."""
        programs: set[str] = set()
        for target in MAKE_CALL.findall(self._doc):
            programs |= self._programs_of(target)
        self.assertIn("uv", programs, sorted(programs))
        for program in sorted(programs):
            self.assertTrue(_word(self._doc, program), f"`{program}` runs but is never named")


if __name__ == "__main__":
    unittest.main()
