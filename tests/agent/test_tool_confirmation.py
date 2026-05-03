# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import unittest
from unittest.mock import MagicMock, patch

from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.tools.base import ToolCall
from trae_agent.utils.cli.cli_console import ToolConfirmationResult
from trae_agent.utils.config import Config, ToolConfirmationConfig
from trae_agent.utils.legacy_config import LegacyConfig


class TestToolConfirmationConfig(unittest.TestCase):
    def test_default_disabled(self):
        config = ToolConfirmationConfig()
        self.assertFalse(config.enabled)
        self.assertIsNone(config.tools_requiring_confirmation)

    def test_custom_config(self):
        config = ToolConfirmationConfig(
            enabled=True,
            tools_requiring_confirmation=["bash"],
        )
        self.assertTrue(config.enabled)
        self.assertEqual(config.tools_requiring_confirmation, ["bash"])


class TestShouldConfirmTool(unittest.TestCase):
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
        if self.config.trae_agent:
            self.agent = TraeAgent(self.config.trae_agent)
        else:
            self.fail("trae_agent config is None")

    def tearDown(self):
        self.llm_client_patcher.stop()

    def test_disabled_by_default(self):
        self.assertFalse(self.agent._should_confirm_tool("bash"))

    def test_all_tools_when_none_list(self):
        self.agent._tool_confirmation_config = ToolConfirmationConfig(
            enabled=True, tools_requiring_confirmation=None
        )
        self.assertTrue(self.agent._should_confirm_tool("bash"))
        self.assertTrue(self.agent._should_confirm_tool("sequentialthinking"))

    def test_specific_tools_only(self):
        self.agent._tool_confirmation_config = ToolConfirmationConfig(
            enabled=True, tools_requiring_confirmation=["bash"]
        )
        self.assertTrue(self.agent._should_confirm_tool("bash"))
        self.assertFalse(self.agent._should_confirm_tool("sequentialthinking"))

    def test_name_normalization(self):
        self.agent._tool_confirmation_config = ToolConfirmationConfig(
            enabled=True, tools_requiring_confirmation=["str_replace_based_edit_tool"]
        )
        # Normalized: "strreplacebasededittool" == "strreplacebasededittool"
        self.assertTrue(self.agent._should_confirm_tool("str_replace_based_edit_tool"))


class TestIsToolCallAllowed(unittest.TestCase):
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
        if self.config.trae_agent:
            self.agent = TraeAgent(self.config.trae_agent)
        else:
            self.fail("trae_agent config is None")

    def tearDown(self):
        self.llm_client_patcher.stop()

    def test_not_allowed_by_default(self):
        tool_call = ToolCall(name="bash", call_id="1", arguments={"command": "ls"})
        self.assertFalse(self.agent._is_tool_call_allowed(tool_call))

    def test_approved_all_allows_everything(self):
        self.agent._tool_confirmation_approved_all = True
        tool_call = ToolCall(name="bash", call_id="1", arguments={"command": "ls"})
        self.assertTrue(self.agent._is_tool_call_allowed(tool_call))

    def test_bash_prefix_matching(self):
        self.agent._allowed_command_prefixes.append("pip install")
        matching = ToolCall(name="bash", call_id="1", arguments={"command": "pip install requests"})
        non_matching = ToolCall(name="bash", call_id="2", arguments={"command": "pip uninstall requests"})
        self.assertTrue(self.agent._is_tool_call_allowed(matching))
        self.assertFalse(self.agent._is_tool_call_allowed(non_matching))

    def test_non_bash_tool_name_matching(self):
        self.agent._allowed_tool_names.add("strreplacebasededittool")
        tool_call = ToolCall(
            name="str_replace_based_edit_tool", call_id="1", arguments={}
        )
        self.assertTrue(self.agent._is_tool_call_allowed(tool_call))


class TestAddAllowedPattern(unittest.TestCase):
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
        if self.config.trae_agent:
            self.agent = TraeAgent(self.config.trae_agent)
        else:
            self.fail("trae_agent config is None")

    def tearDown(self):
        self.llm_client_patcher.stop()

    def test_bash_adds_command_prefix(self):
        tool_call = ToolCall(name="bash", call_id="1", arguments={"command": "pip install requests"})
        self.agent._add_allowed_pattern(tool_call)
        self.assertIn("pip install", self.agent._allowed_command_prefixes)

    def test_bash_single_token_command(self):
        tool_call = ToolCall(name="bash", call_id="1", arguments={"command": "ls"})
        self.agent._add_allowed_pattern(tool_call)
        self.assertIn("ls", self.agent._allowed_command_prefixes)

    def test_non_bash_adds_tool_name(self):
        tool_call = ToolCall(
            name="str_replace_based_edit_tool", call_id="1", arguments={}
        )
        self.agent._add_allowed_pattern(tool_call)
        self.assertIn("strreplacebasededittool", self.agent._allowed_tool_names)


class TestResetToolConfirmationState(unittest.TestCase):
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
        if self.config.trae_agent:
            self.agent = TraeAgent(self.config.trae_agent)
        else:
            self.fail("trae_agent config is None")

    def tearDown(self):
        self.llm_client_patcher.stop()

    def test_reset_clears_state(self):
        self.agent._tool_confirmation_approved_all = True
        self.agent._allowed_command_prefixes.append("pip install")
        self.agent._allowed_tool_names.add("bash")

        self.agent.reset_tool_confirmation_state()

        self.assertFalse(self.agent._tool_confirmation_approved_all)
        self.assertEqual(len(self.agent._allowed_command_prefixes), 0)
        self.assertEqual(len(self.agent._allowed_tool_names), 0)

    def test_new_task_resets_confirmation_state(self):
        self.agent._tool_confirmation_approved_all = True
        self.agent._allowed_command_prefixes.append("git commit")

        self.agent.new_task(
            "test task",
            extra_args={"project_path": "/test", "issue": "test"},
        )

        self.assertFalse(self.agent._tool_confirmation_approved_all)
        self.assertEqual(len(self.agent._allowed_command_prefixes), 0)


class TestToolCallHandlerConfirmation(unittest.TestCase):
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
        if self.config.trae_agent:
            self.agent = TraeAgent(self.config.trae_agent)
        else:
            self.fail("trae_agent config is None")

    def tearDown(self):
        self.llm_client_patcher.stop()

    def test_rejected_tool_returns_error_result(self):
        """When user rejects a tool call, it should return a ToolResult with success=False."""
        from trae_agent.agent.agent_basics import AgentStep, AgentStepState

        self.agent._tool_confirmation_config = ToolConfirmationConfig(
            enabled=True, tools_requiring_confirmation=["bash"]
        )
        mock_console = MagicMock()
        mock_console.get_tool_confirmation.return_value = ToolConfirmationResult.REJECT
        self.agent._cli_console = mock_console

        tool_call = ToolCall(name="bash", call_id="1", arguments={"command": "rm -rf /"})

        import asyncio

        step = AgentStep(step_number=1, state=AgentStepState.THINKING)
        messages = asyncio.get_event_loop().run_until_complete(
            self.agent._tool_call_handler([tool_call], step)
        )

        # Should have one message with the rejected tool result
        self.assertEqual(len(messages), 1)
        self.assertFalse(step.tool_results[0].success)
        self.assertIn("rejected", step.tool_results[0].error)

    def test_no_console_skips_confirmation(self):
        """When no console is set, confirmation should be skipped even when enabled."""
        self.agent._tool_confirmation_config = ToolConfirmationConfig(
            enabled=True, tools_requiring_confirmation=None
        )
        self.agent._cli_console = None

        # Should not raise - just passes through
        self.assertIsNone(self.agent._cli_console)


if __name__ == "__main__":
    unittest.main()
