# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import os
import stat
from pathlib import Path

import pytest

from trae_agent.tools.base import ToolCall
from trae_agent.utils.trajectory_recorder import TrajectoryRecorder


def test_failed_serialization_leaves_last_complete_trajectory(
    tmp_path: Path,
) -> None:
    path = tmp_path / "custom.json"
    recorder = TrajectoryRecorder(str(path))
    recorder.start_recording("Keep the previous result", "test", "test-model", 2)
    before = path.read_bytes()

    recorder.record_agent_step(
        1,
        "COMPLETED",
        tool_calls=[ToolCall(call_id="test", name="test", arguments={"data": [object()]})],
    )

    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_successful_save_replaces_snapshot_at_custom_path(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "custom.json"
    recorder = TrajectoryRecorder(str(path))
    recorder.start_recording("测试", "test", "test-model", 2)
    recorder.record_agent_step(1, "COMPLETED")

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["task"] == "测试"
    assert saved["agent_steps"][0]["step_number"] == 1
    assert list(path.parent.iterdir()) == [path]


def test_replace_failure_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "custom.json"
    recorder = TrajectoryRecorder(str(path))
    recorder.start_recording("Keep the previous result", "test", "test-model", 2)
    before = path.read_bytes()

    def fail_replace(source: Path, target: Path) -> None:
        assert source.parent == target.parent == tmp_path
        assert target.read_bytes() == before
        raise OSError("mock replacement failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    recorder.record_agent_step(1, "COMPLETED")

    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
def test_replacement_keeps_existing_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "custom.json"
    recorder = TrajectoryRecorder(str(path))
    recorder.start_recording("Preserve mode", "test", "test-model", 2)
    path.chmod(0o640)
    recorder.record_agent_step(1, "COMPLETED")

    assert stat.S_IMODE(path.stat().st_mode) == 0o640
