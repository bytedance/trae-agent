from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from trae_agent.tools.mcp_tool import MCPTool


@pytest.mark.asyncio
@pytest.mark.parametrize("texts", [[], ["one", "two"], ["", "second", "third"]])
async def test_success_preserves_all_text_blocks(texts):
    client = AsyncMock()
    client.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text=text) for text in texts]
    )
    tool = MCPTool(client, Tool(name="example", inputSchema={"type": "object"}))
    result = await tool.execute({})
    assert result.error is None
    assert result.output == "\n".join(texts)


@pytest.mark.asyncio
async def test_error_preserves_all_text_blocks():
    client = AsyncMock()
    client.call_tool.return_value = CallToolResult(
        isError=True,
        content=[
            TextContent(type="text", text="failure"),
            TextContent(type="text", text="details"),
        ],
    )
    tool = MCPTool(client, Tool(name="example", inputSchema={"type": "object"}))
    result = await tool.execute({})
    assert result.output is None
    assert result.error == "failure\ndetails"
