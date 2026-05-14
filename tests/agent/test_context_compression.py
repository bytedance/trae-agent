# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the _compress_messages context compression mechanism."""

import unittest
from typing import override
from unittest.mock import MagicMock, patch

from trae_agent.agent.base_agent import BaseAgent
from trae_agent.tools.base import ToolResult
from trae_agent.utils.config import AgentConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage


def make_tool_result(
    name: str, success: bool, result: str | None = None, error: str | None = None
) -> ToolResult:
    return ToolResult(call_id="call_1", name=name, success=success, result=result, error=error)


def make_messages(count: int, with_results: bool = True) -> list[LLMMessage]:
    """Build a synthetic message list of *count* messages."""
    messages = [LLMMessage(role="system", content="You are an expert AI agent.")]
    for i in range(1, count):
        if with_results and i % 2 == 0:
            messages.append(
                LLMMessage(role="user", tool_result=make_tool_result("bash", True, f"output_{i}"))
            )
        else:
            messages.append(LLMMessage(role="assistant", content=f"I will try approach {i}."))
    return messages


class StubAgent(BaseAgent):
    """Minimal BaseAgent subclass for testing _compress_messages."""

    def __init__(self):
        with patch("trae_agent.agent.base_agent.LLMClient") as mock_client:
            mock_client.return_value.client = MagicMock()
            mock_config = MagicMock(spec=AgentConfig)
            mock_config.model = MagicMock()
            mock_config.max_steps = 50
            mock_config.tools = ["bash"]
            super().__init__(mock_config)

    @override
    def new_task(self, task, extra_args=None, tool_names=None):
        pass

    @override
    async def cleanup_mcp_clients(self):
        pass


class TestCompressMessagesThreshold(unittest.TestCase):
    """Compression only triggers at the right step/message thresholds."""

    def setUp(self):
        self.agent = StubAgent()

    def test_no_compression_below_threshold(self):
        """Step not at 10-modulo boundary — no compression."""
        messages = make_messages(10)
        result = self.agent._compress_messages(messages, step_number=5)
        self.assertIs(result, messages)

    def test_no_compression_below_threshold_any_count(self):
        """Step below interval even with many messages — no compression."""
        messages = make_messages(100)
        result = self.agent._compress_messages(messages, step_number=9)
        self.assertIs(result, messages)

    def test_compression_at_boundary(self):
        """Step at boundary — compression triggers (count no longer gated)."""
        messages = make_messages(20)
        result = self.agent._compress_messages(messages, step_number=10)
        self.assertIsNot(result, messages)
        self.assertLess(len(result), len(messages))

    def test_compression_large_list(self):
        """Large list at boundary — compression triggers."""
        messages = make_messages(40)
        result = self.agent._compress_messages(messages, step_number=10)
        self.assertIsNot(result, messages)
        self.assertLess(len(result), len(messages))


class TestCompressMessagesPreservation(unittest.TestCase):
    """Verify critical content is never dropped during compression."""

    def setUp(self):
        self.agent = StubAgent()

    def test_system_prompt_preserved(self):
        messages = make_messages(40)
        result = self.agent._compress_messages(messages, step_number=10)
        self.assertEqual(result[0].role, "system")
        self.assertEqual(result[0].content, messages[0].content)

    def test_last_messages_preserved(self):
        messages = make_messages(40)
        result = self.agent._compress_messages(messages, step_number=10)
        for i in range(1, 16):
            orig = messages[-i]
            compressed = result[-i]
            self.assertEqual(orig.role, compressed.role)
            if orig.tool_result:
                self.assertEqual(orig.tool_result.result, compressed.tool_result.result)

    def test_summary_message_injected(self):
        messages = make_messages(40)
        result = self.agent._compress_messages(messages, step_number=10)
        self.assertEqual(result[1].role, "user")
        self.assertIn("Micro-Compression", result[1].content or "")


class TestCompressMessagesWithFailures(unittest.TestCase):
    """Verify error information is captured in summaries."""

    def setUp(self):
        self.agent = StubAgent()

    def test_failed_tool_results_preserved(self):
        messages = [
            LLMMessage(role="system", content="system prompt"),
            LLMMessage(
                role="user",
                tool_result=make_tool_result(
                    "bash", False, error="timeout: command exceeded limit"
                ),
            ),
        ]
        for i in range(2, 40):
            messages.append(LLMMessage(role="assistant", content=f"step_{i}"))
        result = self.agent._compress_messages(messages, step_number=10)
        summary = result[1].content or ""
        self.assertIn("timeout", summary.lower())

    def test_mixed_success_failure_in_summary(self):
        messages = [
            LLMMessage(role="system", content="system prompt"),
            LLMMessage(
                role="user",
                tool_result=make_tool_result("bash", True, result="compiled successfully"),
            ),
            LLMMessage(
                role="user",
                tool_result=make_tool_result("bash", False, error="file not found"),
            ),
        ]
        for i in range(3, 40):
            messages.append(LLMMessage(role="assistant", content=f"step_{i}"))
        result = self.agent._compress_messages(messages, step_number=10)
        summary = result[1].content or ""
        self.assertIn("compiled", summary)
        self.assertIn("not found", summary)


class TestResetClientHistory(unittest.TestCase):
    """_reset_llm_client_history should suppress errors gracefully."""

    def setUp(self):
        self.agent = StubAgent()

    def test_reset_on_client_with_history(self):
        self.agent._llm_client.client.message_history = ["msg1", "msg2"]
        self.agent._reset_llm_client_history()
        self.assertEqual(self.agent._llm_client.client.message_history, [])

    def test_reset_on_client_without_history(self):
        self.agent._llm_client.client = MagicMock(spec=[])
        self.agent._reset_llm_client_history()

    def test_reset_on_none_client(self):
        self.agent._llm_client.client = None
        self.agent._reset_llm_client_history()


if __name__ == "__main__":
    unittest.main()
