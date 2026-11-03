# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for Docker tool argument shell quoting."""

import json
import shlex
import unittest
from unittest.mock import MagicMock

from trae_agent.tools.base import ToolCall
from trae_agent.tools.docker_tool_executor import DockerToolExecutor


class TestDockerToolArgumentQuoting(unittest.TestCase):
    """Docker tool arguments are passed through a shell, so every value must
    survive quoting: a value containing a single quote used to close the
    argument's quotes early and corrupt the command."""

    def setUp(self):
        self.docker_manager = MagicMock()
        self.docker_manager.CONTAINER_TOOLS_PATH = "/agent_tools"
        self.docker_manager.execute.return_value = (0, "ok")
        self.executor = DockerToolExecutor(
            original_executor=MagicMock(),
            docker_manager=self.docker_manager,
            docker_tools=["bash", "str_replace_based_edit_tool", "json_edit_tool"],
            host_workspace_dir=None,
            container_workspace_dir="/workspace",
        )

    def _run(self, name: str, arguments: dict) -> str:
        self.executor._execute_in_docker(ToolCall(name=name, call_id="call_1", arguments=arguments))
        (command,), _ = self.docker_manager.execute.call_args
        return command

    def test_json_edit_value_with_single_quote_round_trips(self):
        value = {"name": "it's", "nested": {"text": 'say "hi"'}}
        command = self._run(
            "json_edit_tool",
            {"path": "/workspace/data.json", "value": value},
        )

        argv = shlex.split(command)
        self.assertEqual(argv[0], "/agent_tools/json_edit_tool")
        value_index = argv.index("--value")
        # The JSON the container receives must be exactly what was sent.
        self.assertEqual(json.loads(argv[value_index + 1]), value)

    def test_str_replace_arguments_with_single_quote_round_trip(self):
        command = self._run(
            "str_replace_based_edit_tool",
            {
                "command": "str_replace",
                "path": "/workspace/src/app.py",
                "old_str": "greeting = 'hello'",
                "new_str": "greeting = 'it's fine'",
            },
        )

        argv = shlex.split(command)
        self.assertEqual(argv[0], "/agent_tools/edit_tool")
        self.assertEqual(argv[1], "str_replace")
        self.assertEqual(argv[argv.index("--old_str") + 1], "greeting = 'hello'")
        self.assertEqual(argv[argv.index("--new_str") + 1], "greeting = 'it's fine'")

    def test_value_with_spaces_stays_one_argument(self):
        command = self._run(
            "str_replace_based_edit_tool",
            {
                "command": "view",
                "path": "/workspace/my project/file name.py",
            },
        )

        argv = shlex.split(command)
        self.assertEqual(argv[argv.index("--path") + 1], "/workspace/my project/file name.py")

    def test_json_edit_value_with_space_stays_one_argument(self):
        value = {"note": "two words"}
        command = self._run("json_edit_tool", {"path": "/workspace/a.json", "value": value})

        argv = shlex.split(command)
        self.assertEqual(json.loads(argv[argv.index("--value") + 1]), value)

    def test_plain_value_unchanged(self):
        command = self._run(
            "str_replace_based_edit_tool",
            {"command": "view", "path": "/workspace/app.py"},
        )

        argv = shlex.split(command)
        self.assertEqual(argv[argv.index("--path") + 1], "/workspace/app.py")


if __name__ == "__main__":
    unittest.main()
