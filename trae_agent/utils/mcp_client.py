from contextlib import AsyncExitStack
from enum import Enum

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..tools.mcp_tool import MCPTool
from .config import MCPServerConfig


class MCPServerStatus(Enum):
    DISCONNECTED = "disconnected"  # Server is disconnected or experiencing errors
    CONNECTING = "connecting"  # Server is in the process of connecting
    CONNECTED = "connected"  # Server is connected and ready to use


class MCPDiscoveryState(Enum):
    """State of MCP discovery process."""

    NOT_STARTED = "not_started"  # Discovery has not started yet
    IN_PROGRESS = "in_progress"  # Discovery is currently in progress
    # Discovery has completed (with or without errors)
    COMPLETED = "completed"


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self.mcp_servers_status: dict[str, MCPServerStatus] = {}

    def get_mcp_server_status(self, mcp_server_name: str) -> MCPServerStatus:
        return self.mcp_servers_status.get(mcp_server_name, MCPServerStatus.DISCONNECTED)

    def update_mcp_server_status(self, mcp_server_name, status: MCPServerStatus):
        self.mcp_servers_status[mcp_server_name] = status

    async def connect_and_discover(
        self,
        mcp_server_name: str,
        mcp_server_config: MCPServerConfig,
        mcp_tools_container: list,
        model_provider,
    ):
        transport = None
        if mcp_server_config.http_url:
            raise NotImplementedError("HTTP transport is not implemented yet")
        elif mcp_server_config.url:
            raise NotImplementedError("WebSocket transport is not implemented yet")
        elif mcp_server_config.command:
            params = StdioServerParameters(
                command=mcp_server_config.command,
                args=mcp_server_config.args,
                env=mcp_server_config.env,
                cwd=mcp_server_config.cwd,
            )
            transport = await self.exit_stack.enter_async_context(stdio_client(params))
        else:
            # error
            raise ValueError(
                f"Invalid MCP server configuration for {mcp_server_name}. "
                "Please provide either a command or a URL."
            )
        try:
            await self.connect_to_server(mcp_server_name, transport)
            mcp_tools = await self.list_tools()
            for tool in mcp_tools.tools:
                mcp_tool = MCPTool(self, tool, model_provider)
                mcp_tools_container.append(mcp_tool)
        except Exception as e:
            raise e

    async def connect_to_server(self, mcp_server_name, transport):
        """Connect to an MCP server

        Args:
            server_params: Parameters for connecting to the MCP server.
        """
        if self.get_mcp_server_status(mcp_server_name) != MCPServerStatus.CONNECTED:
            self.update_mcp_server_status(mcp_server_name, MCPServerStatus.CONNECTING)
            try:
                stdio, write = transport
                self.session = await self.exit_stack.enter_async_context(
                    ClientSession(stdio, write)
                )
                await self.session.initialize()
                self.update_mcp_server_status(mcp_server_name, MCPServerStatus.CONNECTED)
            except Exception as e:
                self.update_mcp_server_status(mcp_server_name, MCPServerStatus.DISCONNECTED)
                raise e

    async def call_tool(self, name, args):
        output = await self.session.call_tool(name, args)
        return output

    async def list_tools(self):
        tools = await self.session.list_tools()
        return tools

    async def cleanup(self, mcp_server_name):
        """Clean up resources"""
        await self.exit_stack.aclose()
        self.update_mcp_server_status(mcp_server_name, MCPServerStatus.DISCONNECTED)
