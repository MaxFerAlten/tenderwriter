"""Tests for MCP client."""

import pytest

from backend.mcp.client import (
    McpClient,
    McpManager,
    mcp_manager,
)


class TestMcpClient:
    """Tests for MCP client."""

    def test_create_client(self):
        """Test creating an MCP client."""
        client = McpClient(server_command=["echo", "test"], name="test")
        assert client.name == "test"
        assert client.server_command == ["echo", "test"]
        assert client.process is None


class TestMcpManager:
    """Tests for MCP manager."""

    def test_create_manager(self):
        """Test creating an MCP manager."""
        manager = McpManager()
        assert manager.server_count == 0

    def test_module_manager(self):
        """Test module-level manager."""
        assert mcp_manager is not None
        assert isinstance(mcp_manager, McpManager)
