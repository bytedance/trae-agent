"""CLI must accept --value null as JSON null, not as a missing argument."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[2] / "trae_agent" / "tools" / "json_edit_tool_cli.py"


def _run(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    target = tmp_path / "doc.json"
    target.write_text(json.dumps({"name": "old", "other": 1}), encoding="utf-8")
    cmd = [
        sys.executable,
        str(CLI),
        "--operation",
        "set",
        "--file_path",
        str(target),
        "--json_path",
        "$.name",
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True), target


def test_cli_set_null_updates_file(tmp_path: Path) -> None:
    proc, target = _run(tmp_path, "--value", "null")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(target.read_text(encoding="utf-8")) == {"name": None, "other": 1}


def test_cli_missing_value_still_errors(tmp_path: Path) -> None:
    proc, target = _run(tmp_path)
    assert proc.returncode != 0
    assert "required" in (proc.stderr + proc.stdout).lower()
    assert json.loads(target.read_text(encoding="utf-8")) == {"name": "old", "other": 1}


def test_cli_set_false_still_works(tmp_path: Path) -> None:
    proc, target = _run(tmp_path, "--value", "false")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(target.read_text(encoding="utf-8")) == {"name": False, "other": 1}
