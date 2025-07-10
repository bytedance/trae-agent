import unittest

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.sequential_thinking_tool import SequentialThinkingTool

class TestSequentialThinkingTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = SequentialThinkingTool()

    async def test_tool_initialisation(self):
        self.assertEqual(self.tool.get_name(), "sequentialthinking")
        desc = self.tool.get_description()
        self.assertIn("tool helps analyze problems through a flexible", desc)
        self.assertIn("false when truly done and a satisfactory answer is reached", desc)
        params = self.tool.get_parameters()
        names = [p.name for p in params]
        expected = {
            "thought", "next_thought_needed",
            "thought_number", "total_thoughts",
            "is_revision", "revises_thought",
            "branch_from_thought", "branch_id",
            "needs_more_thoughts"
        }
        self.assertEqual(names,expected)

    async def test_missing_required_parameters(self):
        # Missing 'thought'
        result = await self.tool.execute(ToolCallArguments({
            "thought_number": 1, "total_thoughts": 1, "next_thought_needed": False
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("sequential thinking failed", result.error.lower())

        # Missing 'thought_number'
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "total_thoughts": 1, "next_thought_needed": False
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("invalid thought_number", result.error.lower())

        # Missing 'total_thoughts'
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": 1, "next_thought_needed": False
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("invalid total_thoughts", result.error.lower())

        # Missing 'next_thought_needed'
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": 1, "total_thoughts": 1
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("invalid next_thought_needed", result.error.lower())

    async def test_invalid_types_and_values(self):
        # thought_number as string
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": "one", "total_thoughts": 1, "next_thought_needed": False
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("invalid thought_number", result.error.lower())

        # next_thought_needed as non-bool
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": 1, "total_thoughts": 1, "next_thought_needed": "no"
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("invalid next_thought_needed", result.error.lower())

        # thought_number < 1
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": 0, "total_thoughts": 1, "next_thought_needed": False
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("thought_number must be at least 1", result.error.lower())

        # total_thoughts < 1
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": 1, "total_thoughts": 0, "next_thought_needed": False
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("total_thoughts must be at least 1", result.error.lower())

        # invalid revises_thought
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": 2, "total_thoughts": 3,
            "next_thought_needed": True, "is_revision": True,
            "revises_thought": 0
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("revises_thought must be a positive integer", result.error.lower())

        # invalid branch_from_thought
        result = await self.tool.execute(ToolCallArguments({
            "thought": "i need a job", "thought_number": 2, "total_thoughts": 3,
            "next_thought_needed": True,
            "branch_from_thought": 0, "branch_id": "B"
        }))
        self.assertEqual(result.error_code, -1)
        self.assertIn("branch_from_thought must be a positive integer", result.error.lower())

    async def test_format_thought(self):
        result = await self.tool._format_thought(ToolCallArguments({
            "thought": "i need a job", "thought_number": 1, "total_thoughts": 1, "is_revision": True
        }))
        self.assertIn("🔄 Revision", result)

        result = await self.tool._format_thought(ToolCallArguments({
            "thought": "i need a job", "thought_number": 1, "total_thoughts": 1, "branch_from_thought":True
        }))
        self.assertIn("🌿 Branch", result)

        result = await self.tool._format_thought(ToolCallArguments({
            "thought": "i need a job", "thought_number": 1, "total_thoughts": 1,
        }))
        self.assertIn("💭 Thought", result)

if __name__ == "__main__":
    unittest.main()