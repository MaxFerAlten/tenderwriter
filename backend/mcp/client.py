"""MCP Client — interface for Model Context Protocol.

Allows TenderClaw to use external tools provided by MCP servers
(stdio, SSE, etc.). Bridges MCP tools into TenderClaw's tool registry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("tenderclaw.mcp")

_request_counter = 0


def _next_id() -> int:
    global _request_counter
    _request_counter += 1
    return _request_counter


class McpClient:
    """MCP client for stdio-based servers with full tool discovery."""

    def __init__(self, server_command: list[str], name: str = "") -> None:
        self.server_command = server_command
        self.name = name or server_command[0]
        self.process: asyncio.subprocess.Process | None = None
        self._tools: list[dict[str, Any]] = []

    async def connect(self) -> None:
        """Spawn the MCP server process and perform initialization."""
        self.process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Connected to MCP server: %s", self.name)

        # Initialize per MCP spec
        resp = await self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "TenderClaw", "version": "0.1.0"},
        })
        logger.info("MCP server initialized: %s", resp.get("result", {}).get("serverInfo", {}))

        # Send initialized notification
        await self._notify("notifications/initialized", {})

    async def list_tools(self) -> list[dict[str, Any]]:
        """Discover available tools from the MCP server."""
        resp = await self._rpc("tools/list", {})
        self._tools = resp.get("result", {}).get("tools", [])
        logger.info("MCP server %s provides %d tools", self.name, len(self._tools))
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the MCP server."""
        resp = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        result = resp.get("result", {})
        if resp.get("error"):
            result["is_error"] = True
            result["content"] = resp["error"].get("message", "MCP tool error")
        return result

    async def disconnect(self) -> None:
        """Kill the MCP server process."""
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
            self.process = None
            logger.info("Disconnected MCP server: %s", self.name)

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and read the response."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError(f"MCP server {self.name} not connected")

        request = {"jsonrpc": "2.0", "method": method, "params": params, "id": _next_id()}
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        await self.process.stdin.drain()

        line = await asyncio.wait_for(self.process.stdout.readline(), timeout=30)
        if not line:
            raise RuntimeError(f"MCP server {self.name} closed stdout")
        return json.loads(line.decode())

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self.process or not self.process.stdin:
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write((json.dumps(notification) + "\n").encode())
        await self.process.stdin.drain()


class McpManager:
    """Manages multiple MCP server connections."""

    def __init__(self) -> None:
        self._clients: dict[str, McpClient] = {}

    async def add_server(self, name: str, command: list[str]) -> McpClient:
        """Connect to an MCP server and discover its tools."""
        client = McpClient(command, name=name)
        await client.connect()
        await client.list_tools()
        self._clients[name] = client
        return client

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Get all tools from all connected servers, prefixed with server name."""
        all_tools: list[dict[str, Any]] = []
        for server_name, client in self._clients.items():
            for tool in client._tools:
                all_tools.append({
                    **tool,
                    "name": f"mcp_{server_name}_{tool['name']}",
                    "_server": server_name,
                    "_original_name": tool["name"],
                })
        return all_tools

    async def call_tool(self, prefixed_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route a tool call to the correct MCP server."""
        for server_name, client in self._clients.items():
            prefix = f"mcp_{server_name}_"
            if prefixed_name.startswith(prefix):
                original = prefixed_name[len(prefix):]
                return await client.call_tool(original, arguments)
        raise ValueError(f"No MCP server found for tool: {prefixed_name}")

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()

    @property
    def server_count(self) -> int:
        return len(self._clients)


# Module-level instance
mcp_manager = McpManager()
