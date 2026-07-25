# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Load a saved trajectory and prepare it for resumption.

`trae-cli resume <trajectory.json>` uses this to:
  1. Read the JSON trajectory file written by TrajectoryRecorder
  2. Recover the LLM message history at the point of interruption
  3. Recover the completed agent steps for replay
  4. Return everything the CLI needs to spin up a new agent and continue
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trae_agent.utils.llm_clients.llm_basics import LLMMessage, ToolCall, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ResumableTrajectory:
    """A trajectory loaded from disk, ready to be replayed."""

    trajectory_path: Path
    task: str
    provider: str
    model: str
    success: bool
    last_result: str | None
    completed_step_count: int
    # Last input_messages from the last llm_interaction. Contains the
    # full LLM-visible history up to the interruption point.
    last_input_messages: list[LLMMessage] = field(default_factory=list)
    # AgentStep dicts to replay into the new execution.
    completed_steps: list[dict[str, Any]] = field(default_factory=list)
    # Tool calls and results already executed — useful for debugging.
    tool_calls_made: int = 0
    tool_results_recorded: int = 0


class TrajectoryLoadError(Exception):
    """Raised when a trajectory file can't be loaded or resumed."""


def _deserialize_message(data: dict[str, Any]) -> LLMMessage:
    """Reconstruct an LLMMessage from a serialized dict.

    The serialized format is produced by ``TrajectoryRecorder._serialize_message``.
    tool_call / tool_result are optional and reconstructed when present.
    """
    tool_call: ToolCall | None = None
    if data.get("tool_call"):
        tc = data["tool_call"]
        tool_call = ToolCall(
            call_id=tc.get("call_id", ""),
            name=tc.get("name", ""),
            arguments=tc.get("arguments", {}),
            id=tc.get("id"),
        )

    tool_result: ToolResult | None = None
    if data.get("tool_result"):
        tr = data["tool_result"]
        # ToolResult fields are: call_id (not call_call_id — that's a
        # historical name in trajectory_recorder that we tolerate here for
        # backward-compat with older trajectory files), name, success, etc.
        call_id = tr.get("call_id") or tr.get("call_call_id") or ""
        tool_result = ToolResult(
            call_id=call_id,
            name=tr.get("name", ""),
            success=bool(tr.get("success", False)),
            result=tr.get("result"),
            error=tr.get("error"),
            id=tr.get("id"),
        )

    return LLMMessage(
        role=data.get("role", "user"),
        content=data.get("content", "") or "",
        tool_call=tool_call,
        tool_result=tool_result,
    )


def load_trajectory(path: str | Path) -> ResumableTrajectory:
    """Load a trajectory from disk.

    Args:
        path: absolute or relative path to a trajectory JSON file written by
            ``TrajectoryRecorder``.

    Returns:
        ResumableTrajectory populated from the file.

    Raises:
        TrajectoryLoadError: when the file is missing, malformed, or the
            trajectory is already marked as successfully completed (no point
            resuming a done task).
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise TrajectoryLoadError(f"Trajectory file not found: {p}")

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise TrajectoryLoadError(f"Trajectory file is not valid JSON: {e}") from e

    if not isinstance(raw, dict):
        raise TrajectoryLoadError(
            f"Trajectory root must be a JSON object, got {type(raw).__name__}"
        )

    if raw.get("success") is True:
        raise TrajectoryLoadError(
            f"Trajectory at {p.name} is already marked successful; nothing to resume."
        )

    # Recover the LLM-visible message history at the point of interruption.
    # Two sources exist depending on the recorder version:
    #   - llm_interactions[-1].input_messages  (newer / external clients)
    #   - agent_steps[-1].llm_messages         (recorded by BaseAgent)
    # Prefer the longer of the two — that one reflects the most accumulated
    # history. If both are empty, the trajectory can't be resumed.
    interactions = raw.get("llm_interactions") or []
    last_interaction = interactions[-1] if interactions else {}
    inter_msgs_raw = last_interaction.get("input_messages") or []

    completed_steps = list(raw.get("agent_steps") or [])
    last_step = completed_steps[-1] if completed_steps else {}
    step_msgs_raw = last_step.get("llm_messages") or []

    # Pick whichever source has the longer conversation.
    raw_messages = step_msgs_raw if len(step_msgs_raw) >= len(inter_msgs_raw) else inter_msgs_raw

    if not raw_messages:
        raise TrajectoryLoadError(
            f"Trajectory {p.name} has neither llm_interactions nor agent_steps[].llm_messages; "
            f"cannot resume from nothing."
        )

    try:
        last_input_messages = [_deserialize_message(m) for m in raw_messages]
    except Exception as e:
        raise TrajectoryLoadError(
            f"Failed to deserialize recovered messages: {e}"
        ) from e

    # Counters for visibility in the CLI summary
    tool_calls_made = 0
    tool_results_recorded = 0
    for step in completed_steps:
        tool_calls_made += len(step.get("tool_calls") or [])
        tool_results_recorded += len(step.get("tool_results") or [])

    return ResumableTrajectory(
        trajectory_path=p,
        task=raw.get("task", ""),
        provider=raw.get("provider", ""),
        model=raw.get("model", ""),
        success=bool(raw.get("success", False)),
        last_result=raw.get("final_result"),
        completed_step_count=len(completed_steps),
        last_input_messages=last_input_messages,
        completed_steps=completed_steps,
        tool_calls_made=tool_calls_made,
        tool_results_recorded=tool_results_recorded,
    )


def summarize(traj: ResumableTrajectory) -> str:
    """Human-readable summary used by `trae-cli resume` before continuing."""
    return (
        f"task: {traj.task!r}\n"
        f"provider: {traj.provider}  model: {traj.model}\n"
        f"completed steps: {traj.completed_step_count}  "
        f"tool calls: {traj.tool_calls_made}  "
        f"tool results: {traj.tool_results_recorded}\n"
        f"history length: {len(traj.last_input_messages)} messages\n"
        f"last result: {traj.last_result or '(none)'}"
    )
