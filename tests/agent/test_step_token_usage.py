# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""SimpleCLIConsole only shows a per-step "Token Usage" row if the step carries its usage.

These tests drive BaseAgent._run_llm_step with a patched LLMClient, so no API key and no
network calls are involved.
"""

import io
import unittest
from unittest.mock import MagicMock, patch

from rich.console import Console

from trae_agent.agent.agent_basics import AgentExecution, AgentStep, AgentStepState
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.cli.simple_console import SimpleCLIConsole
from trae_agent.utils.config import Config
from trae_agent.utils.legacy_config import LegacyConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage

FIRST_USAGE = LLMUsage(input_tokens=1234, output_tokens=567)
SECOND_USAGE = LLMUsage(input_tokens=2000, output_tokens=800)


def response_with(usage: LLMUsage | None) -> LLMResponse:
    return LLMResponse(content="Let me look at the file.", usage=usage, model="gpt-4")


class TestStepTokenUsage(unittest.IsolatedAsyncioTestCase):
    """A step must record the usage the model reported, or the console row never appears."""

    def setUp(self) -> None:
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
        config = Config.create_from_legacy_config(legacy_config=LegacyConfig(test_config))

        # Avoid creating a real LLMClient, which would need an API key to call.
        patcher = patch("trae_agent.agent.base_agent.LLMClient")
        # The agent holds the instance the patched class returns, so script that one.
        self.llm_client: MagicMock = patcher.start().return_value
        self.addCleanup(patcher.stop)

        agent_config = config.trae_agent
        if agent_config is None:
            self.fail("trae_agent config is None")

        self.agent = TraeAgent(agent_config)
        self.execution = AgentExecution(task="report token usage", steps=[])

    async def run_step(self, usage: LLMUsage | None) -> AgentStep:
        """Drive one real agent step, feeding the agent a canned LLM response."""
        step_number = len(self.execution.steps) + 1
        self.llm_client.chat.return_value = response_with(usage)
        step = AgentStep(step_number=step_number, state=AgentStepState.THINKING)
        messages = [LLMMessage(role="user", content="report token usage")]
        await self.agent._run_llm_step(step, messages, self.execution)
        await self.agent._finalize_step(step, messages, self.execution)
        return step

    async def test_step_records_the_usage_the_model_reported(self):
        step = await self.run_step(FIRST_USAGE)

        self.assertEqual(step.llm_response.usage, FIRST_USAGE)
        self.assertEqual(step.llm_usage, FIRST_USAGE)

    async def test_step_without_usage_records_none_not_zeros(self):
        step = await self.run_step(None)

        self.assertIsNone(step.llm_response.usage)
        self.assertIsNone(step.llm_usage)
        self.assertIsNone(self.execution.total_tokens)

    async def test_later_accumulation_leaves_an_earlier_step_unchanged(self):
        first = await self.run_step(FIRST_USAGE)
        await self.run_step(SECOND_USAGE)

        self.assertEqual(first.llm_usage, FIRST_USAGE)
        self.assertEqual(
            self.execution.total_tokens,
            LLMUsage(input_tokens=3234, output_tokens=1367),
        )

    async def test_console_prints_one_usage_row_per_step_that_has_usage(self):
        console = SimpleCLIConsole()
        console.console = Console(file=io.StringIO(), width=200)
        self.agent.set_cli_console(console)

        await self.run_step(FIRST_USAGE)
        await self.run_step(SECOND_USAGE)
        rendered = console.console.file.getvalue()

        self.assertEqual(rendered.count("Token Usage"), 2)
        self.assertIn("Input: 1234 Output: 567", rendered)
        self.assertIn("Input: 2000 Output: 800", rendered)
        self.assertIn("Input: 3234 Output: 1367", rendered)

        await self.run_step(None)
        rendered = console.console.file.getvalue()

        # Three step tables, but only the two that saw usage get a per-step row.
        self.assertEqual(rendered.count("Completed"), 3)
        self.assertEqual(rendered.count("Token Usage"), 2)


if __name__ == "__main__":
    unittest.main()
