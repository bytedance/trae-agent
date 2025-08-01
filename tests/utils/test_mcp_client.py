import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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
        mock_session = mock_client_session.return_value
        mock_session.initialize = AsyncMock()

        mock_session.call_tool = AsyncMock()

        mcp_servers_dict = {}
        await self.client.connect_and_discover(
            "test_server", config, mcp_servers_dict, model_provider="mock_provider"
        )
        all_tools = []
        for _, tools in mcp_servers_dict.items():
            all_tools.extend(tools)
        self.assertTrue(all(tool.__class__.__name__ == "MCPTool" for tool in all_tools))

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
        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=["tool1", "tool2"])
        self.client.session = mock_session

        result = await self.client.list_tools()
        self.assertEqual(result, ["tool1", "tool2"])

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
