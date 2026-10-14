"""Regression: Docker mode must preserve JSON null for json_edit_tool --value."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from trae_agent.tools.base import ToolCall
from trae_agent.tools.docker_tool_executor import DockerToolExecutor


class _RecordingDockerManager:
    CONTAINER_TOOLS_PATH = "/opt/tools"

    def __init__(self) -> None:
        self.commands: list[str] = []

    def execute(self, command: str) -> tuple[int, str]:
        self.commands.append(command)
        return 0, "ok"


def _make_executor(manager: _RecordingDockerManager) -> DockerToolExecutor:
    return DockerToolExecutor(
        original_executor=MagicMock(),
        docker_manager=manager,  # type: ignore[arg-type]
        docker_tools=["json_edit_tool"],
        host_workspace_dir=None,
        container_workspace_dir="/workspace",
    )


def _command_for(value: Any) -> str:
    manager = _RecordingDockerManager()
    executor = _make_executor(manager)
    tool_call = ToolCall(
        name="json_edit_tool",
        call_id="c1",
        arguments={
            "operation": "set",
            "file_path": "/workspace/a.json",
            "json_path": "$.name",
            "value": value,
        },
    )
    result = executor._execute_in_docker(tool_call)
    assert result.success, result.error
    assert len(manager.commands) == 1
    return manager.commands[0]


def test_docker_json_edit_keeps_null_value_flag() -> None:
    command = _command_for(None)
    assert "--value 'null'" in command
    assert "--operation 'set'" in command
    assert "--json_path '$.name'" in command


def test_docker_json_edit_keeps_zero_and_false() -> None:
    assert "--value '0'" in _command_for(0)
    assert "--value 'false'" in _command_for(False)


def test_docker_json_edit_string_value_is_json_encoded() -> None:
    assert '--value \'"n"\'' in _command_for("n")


def test_docker_json_edit_omits_none_pretty_print() -> None:
    manager = _RecordingDockerManager()
    executor = _make_executor(manager)
    tool_call = ToolCall(
        name="json_edit_tool",
        call_id="c1",
        arguments={
            "operation": "view",
            "file_path": "/workspace/a.json",
            "pretty_print": None,
        },
    )
    result = executor._execute_in_docker(tool_call)
    assert result.success
    command = manager.commands[0]
    assert "--pretty_print" not in command
