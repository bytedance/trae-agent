# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import unittest
from unittest.mock import MagicMock, patch

from trae_agent.agent.agent_basics import AgentError
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.config import Config
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


class TestTraeAgentDockerProjectPath(unittest.TestCase):
    """The Docker task message must use real newlines and the container workspace path."""

    def setUp(self):
        test_config = {
            "default_provider": "anthropic",
            "max_steps": 20,
            "model_providers": {
                "anthropic": {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "test-dummy-api-key",
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

        self.llm_client_patcher = patch("trae_agent.agent.base_agent.LLMClient")
        mock_llm_client = self.llm_client_patcher.start()
        mock_llm_client.return_value.client = MagicMock()

        # Keep the test hermetic: no real container and no Docker tool dispatch.
        self.docker_manager_patcher = patch("trae_agent.agent.base_agent.DockerManager")
        self.mock_docker_manager = self.docker_manager_patcher.start()
        self.mock_docker_manager.return_value.container_workspace = "/workspace"

        self.docker_executor_patcher = patch("trae_agent.agent.base_agent.DockerToolExecutor")
        self.docker_executor_patcher.start()

        if self.config.trae_agent:
            self.agent = TraeAgent(
                self.config.trae_agent,
                docker_config={"workspace_dir": "/host/workspace"},
                docker_keep=True,
            )
        else:
            self.fail("trae_agent config is None")

    def tearDown(self):
        self.llm_client_patcher.stop()
        self.docker_manager_patcher.stop()
        self.docker_executor_patcher.stop()

    def test_docker_project_path_has_real_newlines_and_container_path(self):
        self.agent.new_task("test-task", {"project_path": "/host/workspace", "issue": "Test issue"})

        user_message = self.agent.initial_messages[-1].content
        self.assertIsNotNone(user_message)

        # The path line is terminated by real newlines and points at the container
        # workspace, matching the non-Docker formatting of the same line.
        self.assertIn("[Project root path]:\n/workspace\n\n", user_message)
        # No raw escape sequences should reach the model.
        self.assertNotIn("\\n", user_message)
        self.assertNotIn("\\workspace", user_message)

    def test_non_docker_project_path_uses_host_path(self):
        # The host path branch must keep formatting consistent with the Docker branch.
        self.agent.docker_config = None
        self.agent.new_task("test-task", {"project_path": "/host/workspace", "issue": "Test issue"})

        user_message = self.agent.initial_messages[-1].content
        self.assertIsNotNone(user_message)
        self.assertIn("[Project root path]:\n/host/workspace\n\n", user_message)


if __name__ == "__main__":
    unittest.main()
