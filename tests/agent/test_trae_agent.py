# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from trae_agent.agent.agent_basics import AgentError
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.config import Config
from trae_agent.utils.llm_basics import LLMResponse
from trae_agent.utils.llm_client import LLMClient


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
        self.config = Config(test_config)

        # Avoid create real LLMClient instance to avoid actual API calls
        self.llm_client_patcher = patch("trae_agent.agent.base.LLMClient")
        mock_llm_client = self.llm_client_patcher.start()
        mock_llm_client.return_value.client = MagicMock()

        self.agent = TraeAgent(self.config)
        self.test_project_path = "/test/project"
        self.test_patch_path = "/test/patch.diff"

    def tearDown(self):
        self.llm_client_patcher.stop()

    def test_init_with_mock_client(self):
        """Test initializing TraeAgent with a mock client"""
        # Create a mock LLMClient
        mock_client = MagicMock(spec=LLMClient)
        mock_client.model_parameters = self.config.model_providers["anthropic"]
        mock_client._max_steps = 20

        # Initialize TraeAgent with mock client
        agent = TraeAgent(llm_client=mock_client)

        # Verify agent initialization
        self.assertIsNotNone(agent)
        self.assertEqual(agent.llm_client, mock_client)
        self.assertEqual(agent.model_parameters, mock_client.model_parameters)
        self.assertEqual(agent.max_steps, mock_client.max_steps)
        self.assertEqual(len(agent.initial_messages), 0)
        self.assertEqual(len(agent.tools), 0)

    @patch("trae_agent.utils.trajectory_recorder.TrajectoryRecorder")
    def test_trajectory_setup(self, mock_recorder):
        self.agent.task = "test task"
        _ = self.agent.setup_trajectory_recording()
        self.assertIsNotNone(self.agent.trajectory_recorder)

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
        self.assertEqual(len(self.agent.tools), 5)
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

    @patch("asyncio.create_task")
    @patch("trae_agent.utils.cli_console.CLIConsole")
    def test_task_execution_flow(self, mock_console, mock_task):
        self.agent.set_cli_console(mock_console)
        asyncio.run(self.agent.execute_task())
        mock_console.start.assert_called_once()

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
            self.agent.model_parameters = False

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
        from trae_agent.utils.cli_console import CLIConsole

        mock_console = MagicMock(spec=CLIConsole)
        self.agent.set_cli_console(mock_console)
        self.assertEqual(self.agent.cli_console, mock_console)


if __name__ == "__main__":
    unittest.main()
