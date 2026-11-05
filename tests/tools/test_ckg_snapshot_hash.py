# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Regression tests for the CKG snapshot hash with dirty git files."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from trae_agent.tools.ckg.ckg_database import get_folder_snapshot_hash


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


class TestGitStatusHashDirtyFileContent(unittest.TestCase):
    """Editing an already-dirty file must change the snapshot hash.

    The old hash used git status --porcelain output only, which records the
    file's status flag (e.g. M) but not its content. Editing a file that was
    already dirty left the status unchanged, so the stale CKG database was
    reused and newly added functions could not be found (issue #561).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        _git("init", cwd=self.repo)
        _git("config", "user.email", "test@test.com", cwd=self.repo)
        _git("config", "user.name", "Test", cwd=self.repo)
        (self.repo / "sample.py").write_text("def original(): return 0\n")
        _git("add", ".", cwd=self.repo)
        _git("commit", "-m", "init", cwd=self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def test_second_edit_of_dirty_file_changes_hash(self):
        # First edit: file becomes dirty (status M).
        (self.repo / "sample.py").write_text("def first(): return 1\n")
        hash_first_edit = get_folder_snapshot_hash(self.repo)

        # Second edit: file is still dirty (same status M), but content changed.
        (self.repo / "sample.py").write_text("def second(): return 2\n")
        hash_second_edit = get_folder_snapshot_hash(self.repo)

        self.assertNotEqual(hash_first_edit, hash_second_edit)

    def test_staged_edit_then_restaged_edit_changes_hash(self):
        # Stage an edit.
        (self.repo / "sample.py").write_text("def staged(): return 1\n")
        _git("add", ".", cwd=self.repo)
        hash_staged_1 = get_folder_snapshot_hash(self.repo)

        # Edit again and restage: status line is still "M sample.py".
        (self.repo / "sample.py").write_text("def staged(): return 2\n")
        _git("add", ".", cwd=self.repo)
        hash_staged_2 = get_folder_snapshot_hash(self.repo)

        self.assertNotEqual(hash_staged_1, hash_staged_2)

    def test_clean_repo_hash_unchanged(self):
        """A clean repo keeps the same hash (no diff to include)."""
        hash_1 = get_folder_snapshot_hash(self.repo)
        hash_2 = get_folder_snapshot_hash(self.repo)
        self.assertEqual(hash_1, hash_2)
        self.assertTrue(hash_1.startswith("git-clean-"))


if __name__ == "__main__":
    unittest.main()
