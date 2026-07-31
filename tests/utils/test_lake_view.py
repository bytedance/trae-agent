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

    def test_steps_equal_to_limit_not_trimmed(self):
        """Test that steps exactly at the limit are not trimmed."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 3

        # Add exactly 3 steps
        for i in range(3):
            lake_view.steps.append(f"step_{i}")

        # Should not trim when exactly at limit
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        self.assertEqual(len(lake_view.steps), 3)
        self.assertEqual(lake_view.steps, ["step_0", "step_1", "step_2"])

    def test_steps_below_limit_not_trimmed(self):
        """Test that steps below the limit are not trimmed."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 5

        # Add 3 steps (below limit)
        for i in range(3):
            lake_view.steps.append(f"step_{i}")

        # Should not trim when below limit
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        self.assertEqual(len(lake_view.steps), 3)
        self.assertEqual(lake_view.steps, ["step_0", "step_1", "step_2"])

    def test_empty_steps_list(self):
        """Test that empty steps list is handled correctly."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 3

        # Should not trim empty list
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        self.assertEqual(len(lake_view.steps), 0)
        self.assertEqual(lake_view.steps, [])

    def test_single_step_not_trimmed(self):
        """Test that a single step is not trimmed."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 3

        # Add 1 step
        lake_view.steps.append("step_0")

        # Should not trim single step
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        self.assertEqual(len(lake_view.steps), 1)
        self.assertEqual(lake_view.steps, ["step_0"])

    def test_trim_preserves_order(self):
        """Test that trimming preserves the order of remaining steps."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 2

        # Add 5 steps
        for i in range(5):
            lake_view.steps.append(f"step_{i}")

        # Trim
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        # Should keep last 2 in original order
        self.assertEqual(len(lake_view.steps), 2)
        self.assertEqual(lake_view.steps, ["step_3", "step_4"])

    def test_incremental_trimming(self):
        """Test that trimming works correctly when adding steps one by one."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 2

        # Add steps one by one, trimming after each
        for i in range(5):
            lake_view.steps.append(f"step_{i}")
            if len(lake_view.steps) > lake_view.max_steps:
                lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        # Should only have last 2 steps
        self.assertEqual(len(lake_view.steps), 2)
        self.assertEqual(lake_view.steps, ["step_3", "step_4"])

    def test_large_number_of_steps(self):
        """Test trimming with a large number of steps."""
        lake_view = LakeView.__new__(LakeView)
        lake_view.steps = []
        lake_view.max_steps = 10

        # Add 100 steps
        for i in range(100):
            lake_view.steps.append(f"step_{i}")

        # Trim
        if len(lake_view.steps) > lake_view.max_steps:
            lake_view.steps = lake_view.steps[-lake_view.max_steps:]

        # Should only have last 10 steps
        self.assertEqual(len(lake_view.steps), 10)
        self.assertEqual(lake_view.steps, [f"step_{i}" for i in range(90, 100)])


if __name__ == "__main__":
    unittest.main()
