# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
from datetime import datetime

from trae_agent.utils import trajectory_recorder


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 18, 9, 0, 0, tzinfo=tz)


def test_default_recorders_do_not_overwrite_same_second_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(trajectory_recorder, "datetime", FrozenDatetime)
    first = trajectory_recorder.TrajectoryRecorder()
    first.start_recording("first task", "test", "model", 1)
    first.finalize_recording(True, "first result")
    second = trajectory_recorder.TrajectoryRecorder()
    second.start_recording("second task", "test", "model", 1)
    second.finalize_recording(True, "second result")

    assert first.trajectory_path != second.trajectory_path
    assert json.loads(first.trajectory_path.read_text())["final_result"] == "first result"
    assert json.loads(second.trajectory_path.read_text())["final_result"] == "second result"
    assert first.trajectory_path.name.startswith("trajectory_20261118_090000_")
    assert first.trajectory_path.parent == tmp_path / "trajectories"


def test_explicit_path_is_not_renamed(tmp_path):
    path = tmp_path / "custom" / "run.json"
    recorder = trajectory_recorder.TrajectoryRecorder(str(path))
    recorder.start_recording("task", "test", "model", 1)
    assert recorder.trajectory_path == path
    assert json.loads(path.read_text())["task"] == "task"
