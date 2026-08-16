# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
from pathlib import Path

from trae_agent.utils.trajectory_recorder import TrajectoryRecorder


def test_start_recording_clears_previous_run_state(tmp_path: Path) -> None:
    trajectory_path = tmp_path / "trajectory.json"
    recorder = TrajectoryRecorder(str(trajectory_path))
    recorder.start_recording("first task", "first provider", "first model", 1)
    recorder.trajectory_data["llm_interactions"].append({"stale": True})
    recorder.trajectory_data["agent_steps"].append({"stale": True})
    recorder.finalize_recording(success=True, final_result="first result")

    recorder.start_recording("second task", "second provider", "second model", 2)

    expected = {
        "end_time": "",
        "success": False,
        "final_result": None,
        "execution_time": 0.0,
        "llm_interactions": [],
        "agent_steps": [],
    }
    assert {key: recorder.trajectory_data[key] for key in expected} == expected

    with trajectory_path.open(encoding="utf-8") as trajectory_file:
        saved_trajectory = json.load(trajectory_file)
    assert {key: saved_trajectory[key] for key in expected} == expected
