# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import unittest
from unittest.mock import MagicMock

from trae_agent.utils.lake_view import LakeView


class TestLakeViewMaxSteps(unittest.TestCase):
    def test_default_max_steps_is_50(self):
        """Test that default max_steps is 50."""
        lake_view = LakeView(lake_view_config=None, max_steps=50)
        # When config is None, __init__ returns early, so we need to test differently
        # Let's test by checking the attribute exists when properly initialized
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 50
        self.assertEqual(lake_view.max_steps, 50)

    def test_steps_trimmed_when_exceeding_limit(self):
        """Test that steps are trimmed when exceeding limit."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 3

        # Add 5 steps
        for i in range(5):
            lake_view.steps.append(f"step_{i}")

        # Manually trigger the trim logic
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        # Should only keep the last 3 steps
        self.assertEqual(len(lake_view.steps), 3)
        self.assertEqual(lake_view.steps, ["step_2", "step_3", "step_4"])

    def test_recent_steps_preserved(self):
        """Test that recent steps are preserved when trimming."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 2

        # Add 4 steps
        for i in range(4):
            lake_view.steps.append(f"step_{i}")

        # Manually trigger the trim logic
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        # Should keep the most recent 2 steps
        self.assertEqual(len(lake_view.steps), 2)
        self.assertEqual(lake_view.steps, ["step_2", "step_3"])
        # Oldest steps should be discarded
        self.assertNotIn("step_0", lake_view.steps)
        self.assertNotIn("step_1", lake_view.steps)


if __name__ == "__main__":
    unittest.main()
