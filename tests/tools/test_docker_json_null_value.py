# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Docker command building must not lose an explicit JSON null.

`DockerToolExecutor` renders a `json_edit_tool` call into a shell command for the frozen binary. It
skipped every argument whose value was `None` -- the same marker it uses for "the model did not send
this parameter" -- so a call that sets a field to JSON null reached the binary with no `--value` at
all, and the binary answered that its required arguments were missing. The cases below pin the
rendered command string, which is the whole contract between the executor and the binary.
"""

import unittest
from typing import cast

from trae_agent.agent.docker_manager import DockerManager
from trae_agent.tools.base import ToolCall, ToolCallArguments, ToolExecutor
from trae_agent.tools.docker_tool_executor import DockerToolExecutor


class _StubDockerManager:
    """Records the command the executor builds instead of running it in a container."""

    CONTAINER_TOOLS_PATH = "/opt/tools"

    def __init__(self) -> None:
        self.commands: list[str] = []

    def execute(self, command: str) -> tuple[int, str]:
        self.commands.append(command)
        return 0, ""


def _build_command(tool: str, arguments: dict[str, object]) -> str:
    manager = _StubDockerManager()
    executor = DockerToolExecutor(
        original_executor=ToolExecutor([]),
        docker_manager=cast(DockerManager, manager),
        docker_tools=[tool],
        host_workspace_dir=None,
        container_workspace_dir="/workspace",
    )
    executor._execute_in_docker(
        ToolCall(name=tool, call_id="c1", arguments=cast(ToolCallArguments, arguments))
    )
    assert len(manager.commands) == 1, manager.commands
    return manager.commands[0]


class DockerJsonEditCommandTest(unittest.TestCase):
    _TARGET: dict[str, object] = {
        "operation": "set",
        "file_path": "/workspace/a.json",
        "json_path": "$.name",
    }

    def _for_value(self, value: object) -> str:
        return _build_command("json_edit_tool", {**self._TARGET, "value": value})

    def test_string_value_is_serialized_as_json(self):
        self.assertIn("""--value '"n"'""", self._for_value("n"))

    def test_null_value_is_forwarded_as_json_null(self):
        self.assertIn("--value 'null'", self._for_value(None))

    def test_falsy_values_are_forwarded(self):
        self.assertIn("--value '0'", self._for_value(0))
        self.assertIn("--value 'false'", self._for_value(False))

    def test_absent_value_is_not_invented(self):
        command = _build_command(
            "json_edit_tool", {"operation": "view", "file_path": "/workspace/a.json"}
        )
        self.assertNotIn("--value", command)

    def test_absent_optional_parameters_are_still_skipped(self):
        command = _build_command(
            "json_edit_tool",
            {"operation": "view", "file_path": "/workspace/a.json", "json_path": None},
        )
        self.assertNotIn("--json_path", command)


if __name__ == "__main__":
    unittest.main()
