"""Model Context Protocol (MCP) server management and tool integration."""

import json
import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

CONFIG_PATH = "./mcp_config.json"


class MCPServerError(Exception):
    """Raised when MCP server connection or operation fails."""

    pass


class MCPManager:
    """Manages Model Context Protocol server connections and tool discovery."""

    def __init__(self, config_path: str = CONFIG_PATH):
        """Initialize MCP manager.

        Args:
            config_path: Path to MCP configuration JSON file.
        """
        self.config_path = config_path
        self.servers: dict[str, dict] = {}

    async def _load_configuration(self) -> dict:
        """Load MCP configuration from file.

        Returns:
            Configuration dictionary with server definitions.

        Raises:
            MCPServerError: If configuration file cannot be loaded.
        """
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            raise MCPServerError(f"Configuration file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise MCPServerError(f"Invalid configuration JSON: {e}")

    async def connect_servers(
        self,
    ) -> tuple[AsyncExitStack, list[tuple[str, ClientSession]]]:
        """Connect to all configured MCP servers.

        Returns:
            Tuple of (exit_stack for cleanup, list of (server_name, session) tuples).

        Raises:
            MCPServerError: If no servers can be connected.
        """
        config = await self._load_configuration()
        servers_config = config.get("mcpServers", {})

        if not servers_config:
            raise MCPServerError("No MCP servers configured")

        stack = AsyncExitStack()
        active_sessions = []

        for server_name, server_config in servers_config.items():
            try:
                session = await self._connect_server(stack, server_name, server_config)
                active_sessions.append((server_name, session))
            except Exception as e:
                logger.warning(f"Failed to connect to MCP server '{server_name}': {e}")

        if not active_sessions:
            await stack.aclose()
            raise MCPServerError("Could not connect to any MCP servers")

        return stack, active_sessions

    async def _connect_server(
        self, stack: AsyncExitStack, server_name: str, config: dict
    ) -> ClientSession:
        """Establish connection to a single MCP server.

        Args:
            stack: Async context manager for resource cleanup.
            server_name: Name identifier for the server.
            config: Server configuration with command and args.

        Returns:
            Initialized ClientSession for the server.
        """
        command = config.get("command")
        args = config.get("args", [])
        env = config.get("env")

        if not command:
            raise ValueError(f"Server '{server_name}' missing 'command' in config")

        params = StdioServerParameters(command=command, args=args, env=env)
        stdio_transport = await stack.enter_async_context(stdio_client(params))
        read, write = stdio_transport

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        logger.info(f"Connected to MCP server: {server_name}")
        return session

    async def discover_tools(
        self, sessions: list[tuple[str, ClientSession]]
    ) -> list[dict]:
        """Discover all available tools from connected MCP servers.

        Args:
            sessions: List of (server_name, session) tuples.

        Returns:
            List of tools in OpenAI-compatible function calling format.
        """
        all_tools = []

        for server_name, session in sessions:
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    tool_definition = {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": (
                                tool.inputSchema
                                if tool.inputSchema
                                else {"type": "object", "properties": {}}
                            ),
                        },
                        "_mcp_server": server_name,
                    }
                    all_tools.append(tool_definition)
                logger.info(f"Discovered {len(result.tools)} tools from {server_name}")
            except Exception as e:
                logger.error(f"Failed to discover tools from '{server_name}': {e}")

        return all_tools

    async def execute_tool(
        self,
        sessions: list[tuple[str, ClientSession]],
        tool_name: str,
        arguments: dict,
    ) -> str:
        """Execute a tool on its hosting MCP server.

        Args:
            sessions: List of (server_name, session) tuples.
            tool_name: Name of the tool to execute.
            arguments: Arguments to pass to the tool.

        Returns:
            Tool execution result as string.
        """
        logger.info(f"Executing tool '{tool_name}' with arguments: {arguments}")

        for server_name, session in sessions:
            try:
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]

                if tool_name in tool_names:
                    result = await session.call_tool(tool_name, arguments)
                    return str(result.content)
            except Exception as e:
                logger.debug(f"Tool '{tool_name}' not found in '{server_name}': {e}")
                continue

        error_msg = f"Tool '{tool_name}' not found in any connected MCP server"
        logger.error(error_msg)
        return f"Error: {error_msg}"


# Global instance for backward compatibility
_mcp_manager = MCPManager()


async def connect_all_mcps():
    """Connect to all configured MCP servers using default manager."""
    return await _mcp_manager.connect_servers()


async def get_tools(sessions):
    """Discover tools from sessions using default manager."""
    return await _mcp_manager.discover_tools(sessions)


async def call_tool(sessions, tool_name: str, args: dict) -> str:
    """Execute tool using default manager."""
    return await _mcp_manager.execute_tool(sessions, tool_name, args)
