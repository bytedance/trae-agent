import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

from mcp.types import ListToolsResult, Tool

from trae_agent.utils.mcp_client import MCPClient, MCPServerConfig, MCPServerStatus


class TestMCPClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MCPClient()

    def test_get_default_server_status(self):
        status = self.client.get_mcp_server_status("unknown_server")
        self.assertEqual(status, MCPServerStatus.DISCONNECTED)

    def test_update_and_get_server_status(self):
        self.client.update_mcp_server_status("test_server", MCPServerStatus.CONNECTED)
        status = self.client.get_mcp_server_status("test_server")
        self.assertEqual(status, MCPServerStatus.CONNECTED)

    @patch("trae_agent.utils.mcp_client.ClientSession")
    async def test_connect_to_server(self, mock_client_session):
        mock_transport = (MagicMock(), MagicMock())

        mock_instance = mock_client_session.return_value

        mock_instance.initialize = AsyncMock()

        await self.client.connect_to_server("test_server", mock_transport)

        self.assertEqual(
            self.client.get_mcp_server_status("test_server"), MCPServerStatus.CONNECTED
        )
        # mock_instance.initialize.assert_awaited()

    @patch("trae_agent.utils.mcp_client.stdio_client")
    @patch("trae_agent.utils.mcp_client.ClientSession")
    async def test_connect_and_discover_stdio(self, mock_client_session, mock_stdio_client):
        # Setup mock MCP config
        config = MCPServerConfig(command="echo", args=[], env={}, cwd=".")

        # Mock the returned transport
        mock_stdio = AsyncMock()
        mock_writer = AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio, mock_writer)

        # Mock session and list_tools return
        mock_session = mock_client_session.return_value.__aenter__.return_value
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(
            side_effect=[
                ListToolsResult(tools=[Tool(name="first", inputSchema={})], nextCursor="next"),
                ListToolsResult(tools=[Tool(name="second", inputSchema={})]),
            ]
        )

        discovered_tools = []
        await self.client.connect_and_discover(
            "test_server", config, discovered_tools, model_provider="mock_provider"
        )
        self.addAsyncCleanup(self.client.cleanup, "test_server")
        self.assertEqual([tool.name for tool in discovered_tools], ["first", "second"])
        self.assertEqual(mock_session.list_tools.await_args_list, [call(), call(cursor="next")])

    async def test_connect_and_discover_invalid_config(self):
        config = MCPServerConfig()
        mcp_servers_dict = {}
        with self.assertRaises(ValueError):
            await self.client.connect_and_discover(
                "invalid_server", config, mcp_servers_dict, model_provider=None
            )
        self.assertEqual(len(mcp_servers_dict), 0)

    async def test_call_tool(self):
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value={"result": "ok"})
        self.client.session = mock_session

        result = await self.client.call_tool("tool_name", {"arg1": "val"})
        self.assertEqual(result, {"result": "ok"})

    async def test_list_tools(self):
        response = ListToolsResult(
            tools=[Tool(name="tool1", inputSchema={}), Tool(name="tool2", inputSchema={})]
        )
        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=response)
        self.client.session = mock_session

        result = await self.client.list_tools()
        self.assertIs(result, response)
        mock_session.list_tools.assert_awaited_once_with()

    async def test_list_tools_follows_cursors_through_empty_pages(self):
        first = ListToolsResult(
            tools=[Tool(name="first", inputSchema={})],
            nextCursor="page-2",
            _meta={"source": "server"},
        )
        self.client.session = AsyncMock()
        self.client.session.list_tools.side_effect = [
            first,
            ListToolsResult(tools=[], nextCursor="page-3"),
            ListToolsResult(tools=[Tool(name="last", inputSchema={})]),
        ]

        result = await self.client.list_tools()

        self.assertEqual([tool.name for tool in result.tools], ["first", "last"])
        self.assertIsNone(result.nextCursor)
        self.assertEqual(result.meta, {"source": "server"})
        self.assertEqual(
            self.client.session.list_tools.await_args_list,
            [call(), call(cursor="page-2"), call(cursor="page-3")],
        )

    async def test_list_tools_preserves_empty_cursor(self):
        self.client.session = AsyncMock()
        self.client.session.list_tools.side_effect = [
            ListToolsResult(tools=[], nextCursor=""),
            ListToolsResult(tools=[Tool(name="last", inputSchema={})]),
        ]

        result = await self.client.list_tools()

        self.assertEqual([tool.name for tool in result.tools], ["last"])
        self.assertEqual(self.client.session.list_tools.await_args_list, [call(), call(cursor="")])

    async def test_list_tools_propagates_later_page_error(self):
        self.client.session = AsyncMock()
        self.client.session.list_tools.side_effect = [
            ListToolsResult(tools=[], nextCursor="next"),
            RuntimeError("page request failed"),
        ]

        with self.assertRaisesRegex(RuntimeError, "page request failed"):
            await self.client.list_tools()

    async def test_list_tools_propagates_later_page_cancellation(self):
        self.client.session = AsyncMock()
        self.client.session.list_tools.side_effect = [
            ListToolsResult(tools=[], nextCursor="next"),
            asyncio.CancelledError(),
        ]

        with self.assertRaises(asyncio.CancelledError):
            await self.client.list_tools()

    async def test_cleanup(self):
        self.client.update_mcp_server_status("test_server", MCPServerStatus.CONNECTED)
        self.client.exit_stack.aclose = AsyncMock()

        await self.client.cleanup("test_server")
        self.assertEqual(
            self.client.get_mcp_server_status("test_server"), MCPServerStatus.DISCONNECTED
        )
        self.client.exit_stack.aclose.assert_awaited()


if __name__ == "__main__":
    unittest.main()
