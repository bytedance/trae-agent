import unittest
from unittest.mock import AsyncMock, MagicMock

from trae_agent.tools.base import ToolCallArguments, ToolExecResult
from trae_agent.tools.mcp_tool import MCPTool


class TestMCPTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # simulate a tool schema
        self.mock_tool = MagicMock()
        self.mock_tool.name = "test_tool"
        self.mock_tool.description = "A test tool"
        self.mock_tool.inputSchema = {
            "required": ["param1"],
            "properties": {
                "param1": {"type": "string", "description": "First parameter"},
                "param2": {"type": "integer", "description": "Second parameter"},
            },
        }

        # simulate client side
        self.mock_client = MagicMock()
        self.tool = MCPTool(self.mock_client, self.mock_tool, model_provider="test_provider")

    def test_get_name(self):
        self.assertEqual(self.tool.get_name(), "test_tool")

    def test_get_description(self):
        self.assertEqual(self.tool.get_description(), "A test tool")

    def test_get_model_provider(self):
        self.assertEqual(self.tool.get_model_provider(), "test_provider")

    def test_get_parameters(self):
        params = self.tool.get_parameters()
        self.assertEqual(len(params), 2)
        self.assertTrue(any(p.name == "param1" and p.required for p in params))
        self.assertTrue(any(p.name == "param2" and not p.required for p in params))

    async def test_execute_success(self):
        mock_response = MagicMock()
        mock_response.isError = False
        mock_response.content = [MagicMock(text="Execution successful")]
        self.mock_client.call_tool = AsyncMock(return_value=mock_response)

        arguments = ToolCallArguments(arguments={"param1": "value", "param2": 123})
        result: ToolExecResult = await self.tool.execute(arguments)

        self.assertIsNone(result.error)
        self.assertEqual(result.output, "Execution successful")

    async def test_execute_failure(self):
        mock_response = MagicMock()
        mock_response.isError = True
        mock_response.content = [MagicMock(text="Something went wrong")]
        self.mock_client.call_tool = AsyncMock(return_value=mock_response)

        arguments = ToolCallArguments(arguments={"param1": "value"})
        result: ToolExecResult = await self.tool.execute(arguments)

        self.assertIsNone(result.output)
        self.assertEqual(result.error, "Something went wrong")

    async def test_execute_exception(self):
        self.mock_client.call_tool = AsyncMock(side_effect=RuntimeError("Tool crashed"))

        arguments = ToolCallArguments(arguments={"param1": "value"})
        result: ToolExecResult = await self.tool.execute(arguments)

        self.assertIn("Error running mcp tool", result.error)
        self.assertEqual(result.error_code, -1)


if __name__ == "__main__":
    unittest.main()
