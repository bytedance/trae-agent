# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from trae_agent.agent.agent_basics import AgentError
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.tools.base import ToolCall
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

    def test_cancelled_execution_releases_resources(self):
        asyncio.run(self.check_interrupted_execution("cancel"))

    def test_timed_out_execution_releases_resources(self):
        asyncio.run(self.check_interrupted_execution("timeout"))

    def test_docker_stop_failure_still_closes_tools_and_mcp(self):
        asyncio.run(self.check_cleanup_failure("docker"))

    def test_tool_close_failure_still_closes_mcp(self):
        asyncio.run(self.check_cleanup_failure("tool"))

    async def check_cleanup_failure(self, failing_stage):
        error = RuntimeError(f"{failing_stage} cleanup failed")
        docker = MagicMock()
        self.agent.docker_manager = docker
        self.agent.docker_keep = False
        if failing_stage == "docker":
            docker.stop.side_effect = error
        mcp = MagicMock()
        mcp.cleanup = AsyncMock()
        self.agent.mcp_clients.append(mcp)
        response = LLMResponse(
            content="finished", tool_calls=[ToolCall(name="task_done", call_id="done")]
        )
        with (
            patch.object(self.agent.llm_client, "chat", return_value=response),
            patch.object(self.agent.tools[0], "close", new_callable=AsyncMock) as close_tool,
        ):
            if failing_stage == "tool":
                close_tool.side_effect = error
            with self.assertRaises(RuntimeError) as raised:
                await self.agent.execute_task()
            self.assertIs(raised.exception, error)
            docker.stop.assert_called_once_with()
            close_tool.assert_awaited_once_with()
            mcp.cleanup.assert_awaited_once()
            self.assertEqual(self.agent.mcp_clients, [])

    def test_mcp_cleanup_failure_keeps_successful_result(self):
        asyncio.run(self.check_mcp_cleanup_failure())

    async def check_mcp_cleanup_failure(self):
        mcp = MagicMock()
        mcp.cleanup = AsyncMock(side_effect=RuntimeError("MCP close failed"))
        self.agent.mcp_clients.append(mcp)
        response = LLMResponse(
            content="finished", tool_calls=[ToolCall(name="task_done", call_id="done")]
        )
        with patch.object(self.agent.llm_client, "chat", return_value=response):
            execution = await self.agent.execute_task()
        self.assertTrue(execution.success)
        self.assertEqual(execution.final_result, "finished")
        mcp.cleanup.assert_awaited_once()
        self.assertEqual(self.agent.mcp_clients, [])

    async def check_interrupted_execution(self, interruption):
        started = asyncio.Event()
        tool = self.agent.tools[0]
        response = LLMResponse(
            content="",
            tool_calls=[ToolCall(name=tool.name, call_id="call_1")],
        )

        async def blocked_step(*args):
            started.set()
            await asyncio.Event().wait()

        with (
            patch.object(self.agent.llm_client, "chat", return_value=response),
            patch.object(tool, "execute", side_effect=blocked_step),
            patch.object(tool, "close", new_callable=AsyncMock) as close_tool,
            patch.object(self.agent, "cleanup_mcp_clients", new_callable=AsyncMock) as cleanup_mcp,
        ):
            task = asyncio.create_task(self.agent.execute_task())
            try:
                await asyncio.wait_for(started.wait(), timeout=1)
                if interruption == "cancel":
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    with self.assertRaises(TimeoutError):
                        await asyncio.wait_for(task, timeout=0)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

            close_tool.assert_awaited_once_with()
            cleanup_mcp.assert_awaited_once_with()

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


if __name__ == "__main__":
    unittest.main()
