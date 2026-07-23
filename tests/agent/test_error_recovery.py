# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the error recovery mechanism in BaseAgent.execute_task.

When an unexpected exception is raised during a step, the agent should
format the error as a user message and give the LLM a chance to retry
with a different approach, up to ``max_error_retries`` times.
"""

import unittest
from unittest.mock import MagicMock, patch

from trae_agent.agent.agent_basics import AgentExecution, AgentState, AgentStep, AgentStepState
from trae_agent.agent.base_agent import BaseAgent
from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import AgentConfig, ModelConfig, ModelProvider, TraeAgentConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage


class _TestAgent(BaseAgent):
    """Minimal concrete agent for testing BaseAgent.execute_task."""

    def new_task(
        self, task: str, extra_args: dict[str, str] | None = None, tool_names: list[str] | None = None
    ) -> None:
        self._task = task
        self._initial_messages = [
            LLMMessage(role="system", content="You are a test agent."),
            LLMMessage(role="user", content=task),
        ]

    async def execute_task(self) -> AgentExecution:
        return await super().execute_task()

    async def cleanup_mcp_clients(self) -> None:
        pass


def _make_trae_config(max_steps: int = 5, max_error_retries: int = 2) -> TraeAgentConfig:
    """Build a minimal TraeAgentConfig for testing."""
    return TraeAgentConfig(
        model=ModelConfig(
            model="test-model",
            model_provider=ModelProvider(api_key="dummy", provider="openai"),
            temperature=0.5,
            top_p=1.0,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=1,
        ),
        max_steps=max_steps,
        max_error_retries=max_error_retries,
        allow_mcp_servers=[],
        mcp_servers_config={},
        tools=["bash", "task_done"],
    )


class TestErrorRecoveryMessage(unittest.TestCase):
    """Unit tests for _format_error_recovery_message."""

    def setUp(self) -> None:
        config = _make_trae_config(max_error_retries=2)
        with patch("trae_agent.agent.base_agent.LLMClient"):
            self.agent = _TestAgent(config)

    def test_format_includes_exception_details(self) -> None:
        """The recovery message should contain the exception type and text."""
        error = ValueError("something went wrong")
        msg = self.agent._format_error_recovery_message(error, 1)

        self.assertIn("ValueError", msg.content)
        self.assertIn("something went wrong", msg.content)

    def test_format_includes_attempt_number(self) -> None:
        """The recovery message should include the current attempt count."""
        msg = self.agent._format_error_recovery_message(RuntimeError("x"), 2)

        self.assertIn("2/2", msg.content)
        self.assertIn("recovery attempt", msg.content.lower())

    def test_format_includes_hints(self) -> None:
        """The recovery message should suggest trying a different approach."""
        msg = self.agent._format_error_recovery_message(KeyError("missing"), 1)

        self.assertIn("different approach", msg.content.lower())


class TestMaxErrorRetriesProperty(unittest.TestCase):
    """Tests for the max_error_retries property."""

    def test_default_value(self) -> None:
        """AgentConfig should default to 2 retries."""
        config = TraeAgentConfig.__dataclass_fields__["max_error_retries"]
        self.assertEqual(config.default, 2)

    def test_custom_value(self) -> None:
        """The property should reflect the configured value."""
        cfg = _make_trae_config(max_error_retries=3)
        with patch("trae_agent.agent.base_agent.LLMClient"):
            agent = _TestAgent(cfg)
        self.assertEqual(agent.max_error_retries, 3)

    def test_zero_retries_disables_recovery(self) -> None:
        """Setting max_error_retries to 0 should disable recovery."""
        cfg = _make_trae_config(max_error_retries=0)
        with patch("trae_agent.agent.base_agent.LLMClient"):
            agent = _TestAgent(cfg)
        self.assertEqual(agent.max_error_retries, 0)


class TestErrorRecoveryFlow(unittest.TestCase):
    """Integration-style tests for the execute_task recovery loop."""

    @staticmethod
    def _success_response() -> LLMResponse:
        """Build an LLMResponse that signals task completion."""
        tool_call = ToolCall(name="task_done", call_id="done", arguments={})
        return LLMResponse(
            content="Task completed.",
            tool_calls=[tool_call],
            finish_reason="stop",
            model="test",
            usage=LLMUsage(input_tokens=5, output_tokens=3),
        )

    def setUp(self) -> None:
        self.config = _make_trae_config(max_steps=5, max_error_retries=2)

    def test_recovers_then_succeeds(self) -> None:
        """After an LLM-call exception, inject recovery message and succeed."""
        with patch("trae_agent.agent.base_agent.LLMClient") as mock_llm:
            mock_llm.return_value.chat.side_effect = [
                RuntimeError("API timeout"),   # step 1 → raises
                self._success_response(),       # step 2 (recovery) → success
            ]
            agent = _TestAgent(self.config)
            agent.new_task("test task")

            import asyncio

            result = asyncio.run(agent.execute_task())

        self.assertTrue(result.success)
        self.assertGreaterEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].state, AgentStepState.ERROR)

    def test_gives_up_after_max_retries(self) -> None:
        """When every attempt raises, stop after max_error_retries exhausted."""
        self.config.max_error_retries = 1
        self.config.max_steps = 3

        with patch("trae_agent.agent.base_agent.LLMClient") as mock_llm:
            mock_llm.return_value.chat.side_effect = RuntimeError("always fails")
            agent = _TestAgent(self.config)
            agent.new_task("doomed task")

            import asyncio

            result = asyncio.run(agent.execute_task())

        self.assertFalse(result.success)
        self.assertEqual(result.agent_state, AgentState.ERROR)
        self.assertIn("consecutive errors", result.final_result)
        # step 1 (ERROR) + step 2 (retry, ERROR) → break.
        self.assertEqual(len(result.steps), 2)

    def test_error_counter_resets_after_success(self) -> None:
        """A successful step should reset the consecutive error counter."""
        self.config.max_error_retries = 2
        self.config.max_steps = 5

        # A normal (non-task_done) response — the LLM is still working.
        normal_response = LLMResponse(
            content="OK",
            tool_calls=[ToolCall(name="bash", call_id="bash1", arguments={"command": "ls"})],
            finish_reason="stop",
            model="test",
            usage=LLMUsage(input_tokens=5, output_tokens=3),
        )

        with patch("trae_agent.agent.base_agent.LLMClient") as mock_llm:
            # Simulate: error → recovery → error → recovery → success
            mock_llm.return_value.chat.side_effect = [
                RuntimeError("step 1 fail"),     # 1: ERROR
                normal_response,                  # 2: recovery (bash, not done)
                RuntimeError("step 3 fail"),     # 3: ERROR (counter reset)
                self._success_response(),         # 4: recovery → task_done
            ]
            agent = _TestAgent(self.config)
            agent.new_task("task with intermittent errors")

            import asyncio

            result = asyncio.run(agent.execute_task())

        self.assertTrue(result.success)
        self.assertGreaterEqual(len(result.steps), 4)

    def test_zero_retries_fails_immediately(self) -> None:
        """With max_error_retries=0 the agent should break on the first error."""
        self.config.max_error_retries = 0
        self.config.max_steps = 3

        with patch("trae_agent.agent.base_agent.LLMClient") as mock_llm:
            mock_llm.return_value.chat.side_effect = RuntimeError("boom")
            agent = _TestAgent(self.config)
            agent.new_task("doomed")

            import asyncio

            result = asyncio.run(agent.execute_task())

        self.assertFalse(result.success)
        self.assertEqual(len(result.steps), 1)


if __name__ == "__main__":
    unittest.main()
