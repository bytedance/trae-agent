# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""MCP servers answer with a list of content blocks, and only one of them is text.

`tests/tools/test_mcp_tool.py` fakes blocks with `MagicMock(text=...)`, which answers to
any attribute, so these cases use the real `mcp.types` classes the SDK parses into.
"""

import unittest
from typing import cast

import mcp

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.mcp_tool import MCPTool, content_blocks_to_text


class FakeClient:
    """Stands in for MCPClient: hands back one prepared CallToolResult."""

    def __init__(self, result: mcp.types.CallToolResult) -> None:
        self.result = result

    async def call_tool(self, name: str, arguments: object) -> mcp.types.CallToolResult:
        return self.result


def mcp_tool(result: mcp.types.CallToolResult) -> MCPTool:
    tool_def = mcp.types.Tool(
        name="browser_take_screenshot",
        description="Take a screenshot of the current page",
        inputSchema={"type": "object", "properties": {}},
    )
    return MCPTool(FakeClient(result), tool_def, model_provider="openai")


def call(content: list[mcp.types.ContentBlock], is_error: bool = False) -> mcp.types.CallToolResult:
    return mcp.types.CallToolResult(content=content, isError=is_error)


class TestMCPToolContentBlocks(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.arguments: ToolCallArguments = ToolCallArguments(arguments={})

    async def test_all_text_blocks_survive(self):
        result = await mcp_tool(
            call(
                [
                    mcp.types.TextContent(type="text", text="found 3 matches"),
                    mcp.types.TextContent(type="text", text="in 2 files"),
                ]
            )
        ).execute(self.arguments)

        self.assertEqual(result.output, "found 3 matches\nin 2 files")
        self.assertIsNone(result.error)

    async def test_image_block_is_reported_instead_of_raising(self):
        result = await mcp_tool(
            call(
                [
                    mcp.types.ImageContent(type="image", data="cG5k", mimeType="image/png"),
                    mcp.types.TextContent(type="text", text="Screenshot saved"),
                ]
            )
        ).execute(self.arguments)

        self.assertIsNone(result.error)
        self.assertEqual(result.output, "[image: image/png]\nScreenshot saved")

    async def test_embedded_text_resource_keeps_its_text(self):
        result = await mcp_tool(
            call(
                [
                    mcp.types.EmbeddedResource(
                        type="resource",
                        resource=mcp.types.TextResourceContents(
                            uri="file://notes.md", mimeType="text/markdown", text="# notes"
                        ),
                    )
                ]
            )
        ).execute(self.arguments)

        self.assertEqual(result.output, "# notes")

    async def test_embedded_binary_resource_is_named_by_uri(self):
        result = await mcp_tool(
            call(
                [
                    mcp.types.EmbeddedResource(
                        type="resource",
                        resource=mcp.types.BlobResourceContents(
                            uri="file:///tmp/chart.png", mimeType="image/png", blob="cG5k"
                        ),
                    )
                ]
            )
        ).execute(self.arguments)

        self.assertEqual(result.output, "[resource without text: file:///tmp/chart.png]")

    async def test_resource_link_is_named(self):
        result = await mcp_tool(
            call([mcp.types.ResourceLink(type="resource_link", name="chart", uri="file://c.png")])
        ).execute(self.arguments)

        self.assertEqual(result.output, "[resource link: chart]")

    async def test_empty_content_is_described_not_crashed(self):
        result = await mcp_tool(call([])).execute(self.arguments)

        self.assertIsNone(result.error)
        self.assertEqual(result.output, "(the tool returned no content)")

    async def test_error_result_carries_every_text_block(self):
        result = await mcp_tool(
            call(
                [
                    mcp.types.TextContent(type="text", text="rendering failed"),
                    mcp.types.TextContent(type="text", text="invalid colour"),
                ],
                is_error=True,
            )
        ).execute(self.arguments)

        self.assertIsNone(result.output)
        self.assertEqual(result.error, "rendering failed\ninvalid colour")


class TestContentBlocksToText(unittest.TestCase):
    def test_unsupported_block_type_is_still_visible(self):
        class Unexpected:
            pass

        # The SDK's union can grow; an unknown block must be named, not dropped.
        unknown = cast(mcp.types.ContentBlock, Unexpected())
        self.assertEqual(
            content_blocks_to_text([unknown]),
            "[unsupported content: Unexpected]",
        )


if __name__ == "__main__":
    unittest.main()
