# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for AgentStepState, AgentState, and AgentStep extensions."""

import unittest

from trae_agent.agent.agent_basics import AgentStepState


class TestAgentStepStateNewValues(unittest.TestCase):
    """Verify the new lifecycle states exist and are distinct."""

    def test_planning_state_exists(self):
        self.assertEqual(AgentStepState.PLANNING.value, "planning")

    def test_coding_state_exists(self):
        self.assertEqual(AgentStepState.CODING.value, "coding")

    def test_reviewing_state_exists(self):
        self.assertEqual(AgentStepState.REVIEWING.value, "reviewing")

    def test_waiting_state_exists(self):
        self.assertEqual(AgentStepState.WAITING.value, "waiting")

    def test_retrying_state_exists(self):
        self.assertEqual(AgentStepState.RETRYING.value, "retrying")

    def test_all_states_are_unique(self):
        values = [s.value for s in AgentStepState]
        self.assertEqual(len(values), len(set(values)))

    def test_all_states_count(self):
        # 5 original (THINKING, CALLING_TOOL, REFLECTING, COMPLETED, ERROR)
        # + 5 new (PLANNING, CODING, REVIEWING, WAITING, RETRYING)
        self.assertEqual(len(AgentStepState), 10)

    def test_state_construction_from_string(self):
        state = AgentStepState("planning")
        self.assertIs(state, AgentStepState.PLANNING)
        self.assertEqual(state.name, "PLANNING")


if __name__ == "__main__":
    unittest.main()
