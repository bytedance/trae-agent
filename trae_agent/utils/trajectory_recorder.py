# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# TODO: remove these annotations by defining fine-grained types
# pyright: reportExplicitAny=false
# pyright: reportArgumentType=false
# pyright: reportAny=false

"""Trajectory recording functionality for Trae Agent."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..tools.base import ToolCall, ToolResult
from .llm_basics import LLMMessage, LLMResponse


class TrajectoryRecorder:
    """Records trajectory data for agent execution and LLM interactions."""

    def __init__(self, trajectory_path: str | None = None):
        """Initialize trajectory recorder.

        Args:
            trajectory_path: Path to save trajectory file. If None, generates default path.
        """
        if trajectory_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trajectory_path = f"trajectories/trajectory_{timestamp}.json"

        self.trajectory_path: Path = Path(trajectory_path)
        self.trajectory_data: dict[str, Any] = {
            "task": "",
            "start_time": "",
            "end_time": "",
            "provider": "",
            "model": "",
            "max_steps": 0,
            "llm_interactions": [],
            "agent_steps": [],
            "success": False,
            "final_result": None,
            "execution_time": 0.0,
        }
        self._start_time: datetime | None = None

    def start_recording(self, task: str, provider: str, model: str, max_steps: int) -> None:
        """Start recording a new trajectory.

        Args:
            task: The task being executed
            provider: LLM provider being used
            model: Model name being used
            max_steps: Maximum number of steps allowed
        """
        self._start_time = datetime.now()
        self.trajectory_data.update(
            {
                "task": task,
                "start_time": self._start_time.isoformat(),
                "provider": provider,
                "model": model,
                "max_steps": max_steps,
                "llm_interactions": [],
                "agent_steps": [],
            }
        )
        self.save_trajectory()

    def record_llm_interaction(
        self,
        messages: list[LLMMessage],
        response: LLMResponse,
        provider: str,
        model: str,
        tools: list[Any] | None = None,
    ) -> None:
        """Record an LLM interaction.

        Args:
            messages: Input messages to the LLM
            response: Response from the LLM
            provider: LLM provider used
            model: Model used
            tools: Tools available during the interaction
        """
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "input_messages": [self._serialize_message(msg) for msg in messages],
            "response": {
                "content": response.content,
                "model": response.model,
                "finish_reason": response.finish_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                    "cache_creation_input_tokens": getattr(
                        response.usage, "cache_creation_input_tokens", None
                    )
                    if response.usage
                    else None,
                    "cache_read_input_tokens": getattr(
                        response.usage, "cache_read_input_tokens", None
                    )
                    if response.usage
                    else None,
                    "reasoning_tokens": getattr(response.usage, "reasoning_tokens", None)
                    if response.usage
                    else None,
                },
                "tool_calls": [self._serialize_tool_call(tc) for tc in response.tool_calls]
                if response.tool_calls
                else None,
            },
            "tools_available": [tool.name for tool in tools] if tools else None,
        }

        self.trajectory_data["llm_interactions"].append(interaction)
        self.save_trajectory()

    def record_agent_step(
        self,
        step_number: int,
        state: str,
        llm_messages: list[LLMMessage] | None = None,
        llm_response: LLMResponse | None = None,
        tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
        reflection: str | None = None,
        error: str | None = None,
    ) -> None:
        """Record an agent execution step.

        Args:
            step_number: Step number in the execution
            state: Current state of the agent
            llm_messages: Messages sent to LLM in this step
            llm_response: Response from LLM in this step
            tool_calls: Tool calls made in this step
            tool_results: Results from tool execution
            reflection: Agent reflection on the step
            error: Error message if step failed
        """
        step_data = {
            "step_number": step_number,
            "timestamp": datetime.now().isoformat(),
            "state": state,
            "llm_messages": [self._serialize_message(msg) for msg in llm_messages]
            if llm_messages
            else None,
            "llm_response": {
                "content": llm_response.content,
                "model": llm_response.model,
                "finish_reason": llm_response.finish_reason,
                "usage": {
                    "input_tokens": llm_response.usage.input_tokens if llm_response.usage else None,
                    "output_tokens": llm_response.usage.output_tokens
                    if llm_response.usage
                    else None,
                }
                if llm_response.usage
                else None,
                "tool_calls": [self._serialize_tool_call(tc) for tc in llm_response.tool_calls]
                if llm_response.tool_calls
                else None,
            }
            if llm_response
            else None,
            "tool_calls": [self._serialize_tool_call(tc) for tc in tool_calls]
            if tool_calls
            else None,
            "tool_results": [self._serialize_tool_result(tr) for tr in tool_results]
            if tool_results
            else None,
            "reflection": reflection,
            "error": error,
        }

        self.trajectory_data["agent_steps"].append(step_data)
        self.save_trajectory()

    def finalize_recording(self, success: bool, final_result: str | None = None) -> None:
        """Finalize the trajectory recording.

        Args:
            success: Whether the task completed successfully
            final_result: Final result or output of the task
        """
        end_time = datetime.now()
        self.trajectory_data.update(
            {
                "end_time": end_time.isoformat(),
                "success": success,
                "final_result": final_result,
                "execution_time": (end_time - self._start_time).total_seconds()
                if self._start_time
                else 0.0,
            }
        )

        # Save to file
        self.save_trajectory()

    def save_trajectory(self) -> None:
        """Save the current trajectory data to file."""
        try:
            # Ensure directory exists
            self.trajectory_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.trajectory_path, "w", encoding="utf-8") as f:
                json.dump(self.trajectory_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Warning: Failed to save trajectory to {self.trajectory_path}: {e}")

    def _serialize_message(self, message: LLMMessage) -> dict[str, Any]:
        """Serialize an LLM message to a dictionary."""
        data: dict[str, Any] = {"role": message.role, "content": message.content}

        if message.tool_call:
            data["tool_call"] = self._serialize_tool_call(message.tool_call)

        if message.tool_result:
            data["tool_result"] = self._serialize_tool_result(message.tool_result)

        return data

    def _serialize_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        """Serialize a tool call to a dictionary."""
        return {
            "call_id": tool_call.call_id,
            "name": tool_call.name,
            "arguments": tool_call.arguments,
            "id": getattr(tool_call, "id", None),
        }

    def _serialize_tool_result(self, tool_result: ToolResult) -> dict[str, Any]:
        """Serialize a tool result to a dictionary."""
        return {
            "call_id": tool_result.call_id,
            "success": tool_result.success,
            "result": tool_result.result,
            "error": tool_result.error,
            "id": getattr(tool_result, "id", None),
        }

    def get_trajectory_path(self) -> str:
        """Get the path where trajectory is being saved."""
        return str(self.trajectory_path)
