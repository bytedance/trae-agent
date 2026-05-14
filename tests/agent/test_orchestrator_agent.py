# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the OrchestratorAgent — phase transitions, tool isolation, context handoff."""

import unittest
from unittest.mock import MagicMock, patch

from trae_agent.agent.agent_basics import AgentState, AgentStepState
from trae_agent.agent.orchestrator_agent import (
    MAX_STEPS_PER_PHASE,
    PHASE_TOOL_NAMES,
    OrchestratorAgent,
    OrchestratorPhase,
)
from trae_agent.tools.base import Tool, ToolCall
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse


def make_tool(name: str) -> Tool:
    t = MagicMock(spec=Tool)
    t.get_name.return_value = name
    t.name = name
    return t


class TestOrchestratorPhaseConstants(unittest.TestCase):
    """Verify phase and tool constants are well-formed."""

    def test_all_phases_have_tools(self):
        for phase in OrchestratorPhase:
            self.assertIn(phase, PHASE_TOOL_NAMES)
            self.assertGreater(len(PHASE_TOOL_NAMES[phase]), 0)

    def test_planning_has_no_bash(self):
        planning_tools = PHASE_TOOL_NAMES[OrchestratorPhase.PLANNING]
        self.assertNotIn("bash", planning_tools)

    def test_coding_has_all_tools(self):
        coding_tools = PHASE_TOOL_NAMES[OrchestratorPhase.CODING]
        self.assertIn("bash", coding_tools)
        self.assertIn("task_done", coding_tools)

    def test_reviewing_has_no_task_done(self):
        reviewing_tools = PHASE_TOOL_NAMES[OrchestratorPhase.REVIEWING]
        self.assertIn("bash", reviewing_tools)
        self.assertNotIn("task_done", reviewing_tools)

    def test_max_steps_is_reasonable(self):
        self.assertGreater(MAX_STEPS_PER_PHASE, 5)
        self.assertLessEqual(MAX_STEPS_PER_PHASE, 50)


class TestOrchestratorPhaseDetection(unittest.TestCase):
    """_phase_complete must correctly detect completion signals per phase."""

    def setUp(self):
        self.agent = self._make_agent()

    def _make_agent(self):
        with patch("trae_agent.agent.base_agent.LLMClient"):
            agent = OrchestratorAgent(MagicMock())
            return agent

    def test_planning_detects_completion(self):
        response = LLMResponse(
            content="Plan completed.\n</plan_details>\n</plan_approach>",
            usage=None,
        )
        self.assertTrue(self.agent._phase_complete(OrchestratorPhase.PLANNING, response))

    def test_planning_not_complete(self):
        response = LLMResponse(content="Let me explore the codebase first.", usage=None)
        self.assertFalse(self.agent._phase_complete(OrchestratorPhase.PLANNING, response))

    def test_coding_detects_task_done(self):
        response = LLMResponse(
            content="Done.",
            tool_calls=[ToolCall(name="task_done", call_id="call_1")],
        )
        self.assertTrue(self.agent._phase_complete(OrchestratorPhase.CODING, response))

    def test_coding_not_complete_with_other_tools(self):
        response = LLMResponse(
            content="Let me fix this.",
            tool_calls=[ToolCall(name="bash", call_id="call_1")],
        )
        self.assertFalse(self.agent._phase_complete(OrchestratorPhase.CODING, response))

    def test_reviewing_detects_pass_verdict(self):
        response = LLMResponse(content="**Pass**", usage=None)
        self.assertTrue(self.agent._phase_complete(OrchestratorPhase.REVIEWING, response))

    def test_reviewing_detects_fail_verdict(self):
        response = LLMResponse(content="## Review Verdict\n**Fail**", usage=None)
        self.assertTrue(self.agent._phase_complete(OrchestratorPhase.REVIEWING, response))

    def test_reviewing_not_complete(self):
        response = LLMResponse(content="Let me check the implementation first.", usage=None)
        self.assertFalse(self.agent._phase_complete(OrchestratorPhase.REVIEWING, response))


class TestOrchestratorToolIsolation(unittest.TestCase):
    """Each phase should only have access to its permitted tools."""

    def setUp(self):
        with patch("trae_agent.agent.base_agent.LLMClient"):
            self.agent = OrchestratorAgent(MagicMock())
        # Set up tools for the agent
        self.agent._tools = [
            make_tool("bash"),
            make_tool("str_replace_based_edit_tool"),
            make_tool("sequentialthinking"),
            make_tool("task_done"),
        ]

    def test_planning_tools_exclude_bash(self):
        tools = self.agent._build_phase_tools(OrchestratorPhase.PLANNING)
        names = {t.get_name() for t in tools}
        self.assertNotIn("bash", names)
        self.assertIn("str_replace_based_edit_tool", names)
        self.assertIn("sequentialthinking", names)

    def test_coding_tools_include_all(self):
        tools = self.agent._build_phase_tools(OrchestratorPhase.CODING)
        names = {t.get_name() for t in tools}
        self.assertIn("bash", names)
        self.assertIn("task_done", names)
        self.assertIn("str_replace_based_edit_tool", names)

    def test_reviewing_tools_exclude_task_done(self):
        tools = self.agent._build_phase_tools(OrchestratorPhase.REVIEWING)
        names = {t.get_name() for t in tools}
        self.assertIn("bash", names)
        self.assertNotIn("task_done", names)


class TestOrchestratorContextHandoff(unittest.TestCase):
    """Phase handoff should produce the correct context strings."""

    def setUp(self):
        with patch("trae_agent.agent.base_agent.LLMClient"):
            self.agent = OrchestratorAgent(MagicMock())
        self.agent._task = "Fix the login bug"
        self.agent._project_path = "/home/project"

    def test_initial_context_includes_task(self):
        context = self.agent._build_initial_context()
        self.assertIn("Fix the login bug", context)
        self.assertIn("Project Root", context)

    def test_coding_context_includes_plan(self):
        context = self.agent._build_coding_context("## Plan\n1. Fix auth")
        self.assertIn("Fix the login bug", context)
        self.assertIn("Fix auth", context)
        self.assertIn("task_done", context)

    def test_review_context_includes_changes(self):
        context = self.agent._build_review_context("Changed auth.py")
        self.assertIn("Changed auth.py", context)
        self.assertIn("verdict", context.lower())


class TestOrchestratorFullExecution(unittest.IsolatedAsyncioTestCase):
    """Integration tests for the full 3-phase execution flow."""

    def setUp(self):
        self.llm_patcher = patch("trae_agent.agent.base_agent.LLMClient")
        mock_llm = self.llm_patcher.start()
        self.mock_chat = MagicMock()
        mock_llm.return_value.client.chat = self.mock_chat
        mock_llm.return_value.chat = self.mock_chat

        self.agent = OrchestratorAgent(MagicMock())

        # Set up tools
        from trae_agent.tools.edit_tool import TextEditorTool
        from trae_agent.tools.sequential_thinking_tool import SequentialThinkingTool

        self.agent._tools = [
            TextEditorTool(),
            SequentialThinkingTool(),
        ]

        self.agent._task = "Fix the login bug"
        # Add initial messages (for new_task compatibility)
        self.agent._initial_messages = [
            LLMMessage(role="system", content="system"),
            LLMMessage(role="user", content="Fix the login bug"),
        ]

    def tearDown(self):
        self.llm_patcher.stop()

    async def test_phase_sequence_three_phases(self):
        """Verify execute_task runs all 3 phases."""
        self.mock_chat.side_effect = [
            LLMResponse(content="Plan completed.\n</plan_details>\n</plan_approach>", usage=None),  # Planning
            LLMResponse(
                content="Done.",
                tool_calls=[ToolCall(name="task_done", call_id="call_1")],
            ),  # Coding
            # Reviewing: must call bash before verdict (C4 enforcement)
            LLMResponse(
                content="Running tests...",
                tool_calls=[ToolCall(name="bash", call_id="call_bash")],
            ),
            LLMResponse(content="## Review Verdict\n**Pass**", usage=None),
        ]

        execution = await self.agent.execute_task()

        self.assertTrue(execution.success)
        self.assertEqual(execution.agent_state, AgentState.COMPLETED)
        self.assertIn("Plan", execution.final_result)
        self.assertIn("Result", execution.final_result)
        self.assertIn("Review", execution.final_result)
        # Should have at least 4 steps (one per phase + bash call)
        self.assertGreaterEqual(len(execution.steps), 4)

    async def test_all_steps_have_phase_states(self):
        """Each step should have the correct phase state value."""
        self.mock_chat.side_effect = [
            LLMResponse(content="Plan completed.\n</plan_details>\n</plan_approach>", usage=None),
            LLMResponse(
                content="Done.",
                tool_calls=[ToolCall(name="task_done", call_id="call_1")],
            ),
            # Reviewing: must call bash before verdict (C4 enforcement)
            LLMResponse(
                content="Checking lint...",
                tool_calls=[ToolCall(name="bash", call_id="call_bash")],
            ),
            LLMResponse(content="## Review Verdict\n**Pass**", usage=None),
        ]

        execution = await self.agent.execute_task()

        # Check step states
        step_states = [s.state for s in execution.steps]
        self.assertIn(AgentStepState.PLANNING, step_states)
        self.assertIn(AgentStepState.CODING, step_states)
        self.assertIn(AgentStepState.REVIEWING, step_states)

    async def test_error_during_phase_returns_gracefully(self):
        """Exception in a phase should not crash the entire execution."""
        self.mock_chat.side_effect = Exception("LLM API error")

        execution = await self.agent.execute_task()

        # Should not crash — execution should handle the error
        self.assertIsNotNone(execution.final_result)


class TestOrchestratorAgentType(unittest.TestCase):
    """Verify OrchestratorAgent is registered in the Agent factory."""

    def test_agent_type_enum_exists(self):
        from trae_agent.agent.agent import AgentType

        self.assertIn("OrchestratorAgent", AgentType.__members__)

    def test_orchestrator_value(self):
        from trae_agent.agent.agent import AgentType

        self.assertEqual(AgentType.OrchestratorAgent.value, "orchestrator_agent")


if __name__ == "__main__":
    unittest.main()
