# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from trae_agent.agent.agent_basics import AgentError
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.config import Config, MCPServerConfig
from trae_agent.utils.legacy_config import LegacyConfig
from trae_agent.utils.llm_clients.llm_basics import LLMResponse


class TestTraeAgentExtended(unittest.TestCase):
    def setUp(self):
        test_config = {
            "default_provider": "anthropic",
            "max_steps": 20,
            "model_providers": {
                "anthropic": {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "test-dummy-api-key",  # dummy api key
                    "max_tokens": 4096,
                    "temperature": 0.5,
                    "top_p": 1,
                    "top_k": 0,
                    "parallel_tool_calls": False,
                    "max_retries": 10,
                }
            },
        }
        self.config = Config.create_from_legacy_config(legacy_config=LegacyConfig(test_config))

        # Avoid create real LLMClient instance to avoid actual API calls
        self.llm_client_patcher = patch("trae_agent.agent.base_agent.LLMClient")
        mock_llm_client = self.llm_client_patcher.start()
        mock_llm_client.return_value.client = MagicMock()

        if self.config.trae_agent:
            self.agent = TraeAgent(self.config.trae_agent)
        else:
            self.fail("trae_agent config is None")
        self.test_project_path = "/test/project"
        self.test_patch_path = "/test/patch.diff"

    def tearDown(self):
        self.llm_client_patcher.stop()

    def test_new_task_initialization(self):
        with self.assertRaises(AgentError):
            self.agent.new_task("test", {})  # Missing required params

        valid_args = {
            "project_path": self.test_project_path,
            "issue": "Test issue",
            "base_commit": "abc123",
            "must_patch": "true",
            "patch_path": self.test_patch_path,
        }
        self.agent.new_task("test-task", valid_args)

        self.assertEqual(self.agent.project_path, self.test_project_path)
        self.assertEqual(self.agent.must_patch, "true")
        self.assertEqual(len(self.agent.tools), 4)
        self.assertTrue(any(tool.get_name() == "bash" for tool in self.agent.tools))

    @patch("subprocess.check_output")
    @patch("os.chdir")
    @patch("os.path.isdir", return_value=True)
    def test_git_diff_generation(self, mock_isdir, mock_chdir, mock_subprocess):
        mock_subprocess.return_value = b"test diff"
        self.agent.project_path = self.test_project_path

        diff = self.agent.get_git_diff()
        self.assertEqual(diff, "test diff")
        mock_subprocess.assert_called_with(["git", "--no-pager", "diff"])

    def test_patch_filtering(self):
        test_patch = """diff --git a/tests/test_example.py b/tests/test_example.py
--- a/tests/test_example.py
+++ b/tests/test_example.py
@@ -5,6 +5,7 @@
     def test_example(self):
         assert True
"""
        filtered = self.agent.remove_patches_to_tests(test_patch)
        self.assertEqual(filtered, "")

    def test_task_completion_detection(self):
        mock_response = MagicMock(spec=LLMResponse)

        # Test empty patch scenario
        self.agent.must_patch = "true"
        self.assertFalse(self.agent._is_task_completed(mock_response))

        # Test valid patch scenario
        with patch.object(self.agent, "get_git_diff", return_value="valid patch"):
            self.assertTrue(self.agent._is_task_completed(mock_response))

    def test_tool_initialization(self):
        tools = [
            "bash",
            "str_replace_based_edit_tool",
            "sequentialthinking",
            "task_done",
        ]
        self.agent.new_task("test", {"project_path": self.test_project_path}, tools)
        tool_names = [tool.get_name() for tool in self.agent.tools]

        self.assertEqual(len(self.agent.tools), len(tools))
        self.assertIn("bash", tool_names)
        self.assertIn("str_replace_based_edit_tool", tool_names)
        self.assertIn("sequentialthinking", tool_names)
        self.assertIn("task_done", tool_names)

    def test_protected_attributes_access_restrictions(self):
        """Test that protected attributes cannot be accessed directly from outside the class."""

        # Test that accessing protected attributes raises AttributeError
        with self.assertRaises(AttributeError):
            self.agent.llm_client = 5

        with self.assertRaises(AttributeError):
            self.agent.max_steps = None

        with self.assertRaises(AttributeError):
            self.agent.model_config = False

        with self.assertRaises(AttributeError):
            self.agent.initial_messages = "random"

        with self.assertRaises(AttributeError):
            _ = self.agent.tool_caller

    def test_public_property_access_allowed(self):
        """Test that public properties can be accessed properly."""

        # Test that public properties work correctly
        self.assertIsNotNone(self.agent.llm_client)
        self.assertIsNone(self.agent.cli_console)

        # Test that public property setters work
        from trae_agent.utils.cli import CLIConsole

        mock_console = MagicMock(spec=CLIConsole)
        self.agent.set_cli_console(mock_console)
        self.assertEqual(self.agent.cli_console, mock_console)

    def test_mcp_tools_are_refreshed_between_tasks(self):
        class FakeMCPClient:
            instances = []

            def __init__(self):
                self.cleaned = False
                self.tool = SimpleNamespace(name="mcp_tool", client=self)
                self.instances.append(self)

            async def connect_and_discover(self, server_name, config, tools, model_provider):
                tools.append(self.tool)

            async def cleanup(self, server_name):
                self.cleaned = True

        async def run_test():
            self.agent.mcp_servers_config = {"test_server": MCPServerConfig(command="test")}
            self.agent.allow_mcp_servers = ["test_server"]
            self.agent._llm_client.provider.value = "anthropic"
            native_tools = list(self.agent.tools)

            with patch("trae_agent.agent.trae_agent.MCPClient", FakeMCPClient):
                await self.agent.initialise_mcp()
                first_tool = self.agent.mcp_tools[0]
                self.assertIs(self.agent._tool_caller.tools["mcptool"], first_tool)

                await self.agent.cleanup_mcp_clients()
                await self.agent.initialise_mcp()

            self.assertEqual([tool.name for tool in self.agent.tools].count("mcp_tool"), 1)
            self.assertEqual(self.agent.tools[: len(native_tools)], native_tools)
            self.assertIsNot(self.agent.mcp_tools[0], first_tool)
            self.assertIs(self.agent._tool_caller.tools["mcptool"], self.agent.mcp_tools[0])
            self.assertTrue(FakeMCPClient.instances[0].cleaned)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
