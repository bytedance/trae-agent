# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Integration tests: micro-compression inside OrchestratorAgent._run_phase.

Covers TC-1 through TC-4 from the review-v4 test matrix:
  TC-1: step-interval threshold triggers compression
  TC-2: consecutive errors trigger compression
  TC-3: compression calls _reset_llm_client_history()
  TC-4: silent skip when conditions are not met
"""

import unittest
from unittest.mock import MagicMock, patch

from trae_agent.agent.orchestrator_agent import OrchestratorAgent
from trae_agent.compression.types import CompressionTrigger
from trae_agent.tools.base import ToolCall, ToolResult
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse


class TestOrchestratorCompression(unittest.IsolatedAsyncioTestCase):
    """Integration tests for OrchestratorAgent micro-compression."""

    def setUp(self) -> None:
        self.llm_patcher = patch("trae_agent.agent.base_agent.LLMClient")
        mock_llm_cls = self.llm_patcher.start()
        self.mock_chat = MagicMock()
        # Wire both .chat and .client.chat paths since the orchestrator
        # calls self._llm_client.chat() directly.
        mock_llm_cls.return_value.client.chat = self.mock_chat
        mock_llm_cls.return_value.chat = self.mock_chat

        self.agent = OrchestratorAgent(MagicMock())
        self.agent._task = "Test task"
        self.agent._initial_messages = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(role="user", content="task"),
        ]

    def tearDown(self) -> None:
        self.llm_patcher.stop()

    # ── TC-1: step-interval threshold ─────────────────────────────────

    async def test_coding_phase_triggers_compression_at_step_interval(self) -> None:
        """After enough steps, coding phase triggers micro-compression."""
        # Phase breakdown:
        #   Planning:  1 call → "Plan completed."
        #   Coding:   10 plain-text steps + 1 task_done call
        #   Reviewing: 1 call → "Pass"
        responses: list[LLMResponse] = [
            LLMResponse(content="Plan completed.", usage=None),
        ]
        for i in range(10):
            responses.append(LLMResponse(content=f"coding step {i}", usage=None))
        responses.append(LLMResponse(
            content="Done.",
            tool_calls=[ToolCall(name="task_done", call_id="td")],
            usage=None,
        ))
        responses.append(LLMResponse(content="## Review Verdict\n**Pass**", usage=None))
        self.mock_chat.side_effect = responses

        with patch.object(
            self.agent._micro_compressor,
            "compress",
            wraps=self.agent._micro_compressor.compress,
        ) as spy:
            execution = await self.agent.execute_task()
            self.assertTrue(spy.called, "Compression should fire at step interval")
            self.assertTrue(execution.success, "Orchestration should complete")

    # ── TC-2: consecutive errors trigger ──────────────────────────────

    async def test_consecutive_errors_trigger_compression(self) -> None:
        """3 consecutive errors trigger micro-compression."""
        responses: list[LLMResponse] = [
            LLMResponse(content="Plan completed.", usage=None),
        ]
        for i in range(3):
            responses.append(LLMResponse(
                content=f"try {i}",
                tool_calls=[ToolCall(name="bash", call_id=f"e{i}")],
                usage=None,
            ))
        responses.append(LLMResponse(
            content="Done.",
            tool_calls=[ToolCall(name="task_done", call_id="td")],
            usage=None,
        ))
        responses.append(LLMResponse(content="## Review Verdict\n**Pass**", usage=None))
        self.mock_chat.side_effect = responses

        failing = ToolResult(call_id="e0", name="bash", success=False, error="fail")
        with (
            patch("trae_agent.tools.base.ToolExecutor.sequential_tool_call",
                  return_value=[failing]) as _mock_exec,
        ):
            with patch.object(
                self.agent._micro_compressor,
                "compress",
                wraps=self.agent._micro_compressor.compress,
            ) as spy:
                execution = await self.agent.execute_task()
                self.assertTrue(spy.called,
                                "Compression should fire after 3 consecutive errors")
                self.assertTrue(execution.success,
                                "Orchestration should complete")

    # ── TC-3: client history reset ────────────────────────────────────

    async def test_compression_resets_client_history(self) -> None:
        """Compression must call _reset_llm_client_history()."""
        responses: list[LLMResponse] = [
            LLMResponse(content="Plan completed.", usage=None),
        ]
        for i in range(10):
            responses.append(LLMResponse(content=f"coding step {i}", usage=None))
        responses.append(LLMResponse(
            content="Done.",
            tool_calls=[ToolCall(name="task_done", call_id="td")],
            usage=None,
        ))
        responses.append(LLMResponse(content="## Review Verdict\n**Pass**", usage=None))
        self.mock_chat.side_effect = responses

        with patch.object(self.agent, "_reset_llm_client_history") as spy:
            await self.agent.execute_task()
            self.assertTrue(spy.called,
                            "_reset_llm_client_history() should be called after compression")

    # ── T-1: semantic trigger on "step completed" keyword ─────────────

    async def test_semantic_trigger_on_step_completed_keyword(self) -> None:
        """LLM response containing 'step completed' triggers SEMANTIC compression."""
        responses: list[LLMResponse] = [
            LLMResponse(content="Plan completed.", usage=None),
            # Coding step 1: content triggers semantic match
            LLMResponse(content="step completed, results look good", usage=None),
            # Coding step 2: compression fires → task_done completes phase
            LLMResponse(
                content="Done.",
                tool_calls=[ToolCall(name="task_done", call_id="td")],
                usage=None,
            ),
            LLMResponse(content="## Review Verdict\n**Pass**", usage=None),
        ]
        self.mock_chat.side_effect = responses

        compress_reports: list = []
        real_compress = self.agent._micro_compressor.compress

        def _capture(
            messages: list,
            ctx: object,
        ) -> tuple:
            result = real_compress(messages, ctx)
            compress_reports.append(result[1])
            return result

        with patch.object(
            self.agent._micro_compressor,
            "compress",
            side_effect=_capture,
        ) as spy:
            execution = await self.agent.execute_task()
            self.assertTrue(spy.called,
                            "Compression should fire on semantic keyword")
            self.assertTrue(execution.success,
                            "Orchestration should complete")
            self.assertGreater(len(compress_reports), 0,
                               "At least one compression report should exist")
            self.assertEqual(
                compress_reports[0].trigger,
                CompressionTrigger.SEMANTIC,
                "Report trigger must be SEMANTIC when keyword is present",
            )

    # ── TC-4: no compression below threshold ──────────────────────────

    async def test_no_compression_below_interval(self) -> None:
        """Fewer steps than the interval should not trigger compression."""
        responses: list[LLMResponse] = [
            LLMResponse(content="Plan completed.", usage=None),
            # Coding phase: just 1 step + task_done (well below interval)
            LLMResponse(content="step 1", usage=None),
            LLMResponse(
                content="Done.",
                tool_calls=[ToolCall(name="task_done", call_id="td")],
                usage=None,
            ),
            LLMResponse(content="## Review Verdict\n**Pass**", usage=None),
        ]
        self.mock_chat.side_effect = responses

        with patch.object(self.agent._micro_compressor, "compress") as spy:
            execution = await self.agent.execute_task()
            spy.assert_not_called()
            self.assertTrue(execution.success,
                            "Orchestration should complete without compression")
