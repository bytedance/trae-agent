# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import subprocess
from pathlib import Path

import pytest

from trae_agent.tools.ckg import ckg_database
from trae_agent.tools.ckg.ckg_database import get_folder_snapshot_hash
from trae_agent.tools.ckg_tool import CKGTool


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "--quiet")
    (project / "sample.py").write_text("def original():\n    return 0\n", encoding="utf-8")
    git(project, "add", "sample.py")
    git(
        project,
        "-c",
        "user.name=Test User",
        "-c",
        "user.email=test@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "Initial test fixture",
    )
    return project


@pytest.mark.parametrize("state", ["unstaged", "staged", "untracked"])
@pytest.mark.parametrize(
    "contents",
    [(b"def first():\n    return 1\n", b"def later():\n    return 2\n"), (b"\0first", b"\0later")],
    ids=["text", "binary"],
)
def test_snapshot_changes_with_dirty_file_contents(
    repo: Path, state: str, contents: tuple[bytes, bytes]
):
    source = repo / ("new dir/新 file.py" if state == "untracked" else "sample.py")
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(contents[0])
    if state == "staged":
        git(repo, "add", "sample.py")
    status = git(repo, "status", "--porcelain")
    snapshot = get_folder_snapshot_hash(repo)

    source.write_bytes(contents[1])
    if state == "staged":
        git(repo, "add", "sample.py")

    assert git(repo, "status", "--porcelain") == status
    assert get_folder_snapshot_hash(repo) != snapshot
    assert get_folder_snapshot_hash(repo) == get_folder_snapshot_hash(repo)


def test_clean_snapshot_is_stable(repo: Path):
    snapshot = get_folder_snapshot_hash(repo)
    assert snapshot == f"git-clean-{git(repo, 'rev-parse', 'HEAD').strip()}"
    assert get_folder_snapshot_hash(repo) == snapshot


@pytest.mark.parametrize("untracked", [False, True], ids=["tracked", "untracked"])
async def test_new_tool_finds_function_after_another_dirty_edit(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untracked: bool
):
    cache = tmp_path / "cache"
    monkeypatch.setattr(ckg_database, "CKG_DATABASE_PATH", cache)
    monkeypatch.setattr(ckg_database, "CKG_STORAGE_INFO_FILE", cache / "storage_info.json")
    source = repo / ("new.py" if untracked else "sample.py")
    source.write_text("def first():\n    return 1\n", encoding="utf-8")
    tool = CKGTool()
    result = await tool.execute(
        {"command": "search_function", "path": str(repo), "identifier": "first"}
    )
    assert result.output is not None and "Found 1 functions named first" in result.output
    del tool  # Close the first tool's SQLite connection before reopening its cache.

    source.write_text("def later():\n    return 2\n", encoding="utf-8")
    tool = CKGTool()
    result = await tool.execute(
        {"command": "search_function", "path": str(repo), "identifier": "later"}
    )
    assert result.output is not None and "Found 1 functions named later" in result.output
    result = await tool.execute(
        {"command": "search_function", "path": str(repo), "identifier": "first"}
    )
    assert result.output == "No functions named first found."
