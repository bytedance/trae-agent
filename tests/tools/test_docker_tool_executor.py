# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import shlex
from unittest.mock import MagicMock

import pytest

from trae_agent.tools.base import ToolCall
from trae_agent.tools.docker_tool_executor import DockerToolExecutor


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        (
            "str_replace_based_edit_tool",
            {
                "command": "str_replace",
                "path": "/workspace/O'Brien/app.py",
                "old_str": "print('old')",
                "new_str": "print('new')\n# $(echo data); still text",
            },
            [
                "/opt/trae tools/edit_tool",
                "str_replace",
                "--path",
                "/workspace/O'Brien/app.py",
                "--old_str",
                "print('old')",
                "--new_str",
                "print('new')\n# $(echo data); still text",
            ],
        ),
        (
            "json_edit_tool",
            {
                "operation": "set",
                "file_path": "/workspace/O'Brien/config.json",
                "json_path": "$['display name']",
                "value": {"name": "O'Reilly", "text": "a\nb"},
                "pretty_print": False,
            },
            [
                "/opt/trae tools/json_edit_tool",
                "--operation",
                "set",
                "--file_path",
                "/workspace/O'Brien/config.json",
                "--json_path",
                "$['display name']",
                "--value",
                json.dumps({"name": "O'Reilly", "text": "a\nb"}),
                "--pretty_print",
                "False",
            ],
        ),
        (
            "str_replace_based_edit_tool",
            {"command": "view", "path": "/workspace/main.py", "view_range": [1, 3]},
            [
                "/opt/trae tools/edit_tool",
                "view",
                "--path",
                "/workspace/main.py",
                "--view_range",
                "1",
                "3",
            ],
        ),
    ],
)
def test_structured_tool_arguments_survive_shell_parsing(name, arguments, expected):
    manager = MagicMock()
    manager.CONTAINER_TOOLS_PATH = "/opt/trae tools"
    manager.execute.return_value = (0, "ok")
    executor = DockerToolExecutor(MagicMock(), manager, [name], None, "/workspace")

    result = executor._execute_in_docker(ToolCall(call_id="call-1", name=name, arguments=arguments))

    assert result.success
    command = manager.execute.call_args.args[0]
    assert shlex.split(command) == expected


def test_bash_command_is_forwarded_as_shell_code():
    manager = MagicMock()
    manager.execute.return_value = (0, "ok")
    executor = DockerToolExecutor(MagicMock(), manager, ["bash"], None, "/workspace")
    command = "printf '%s' hello | cat"

    result = executor._execute_in_docker(
        ToolCall(call_id="call-1", name="bash", arguments={"command": command})
    )

    assert result.success
    manager.execute.assert_called_once_with(command)
