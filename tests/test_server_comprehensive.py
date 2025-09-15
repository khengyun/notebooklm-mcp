"""
Comprehensive tests for NotebookLM MCP server module
"""

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest

try:
    from mcp.types import CallToolResult, TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    # Mock MCP types for testing when not available
    Tool = Dict[str, Any]
    TextContent = Dict[str, Any]
    CallToolResult = Dict[str, Any]

from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.server import NotebookLMFastMCP


class TestNotebookLMServerInitialization:
    """Test server initialization and configuration"""

    def test_server_initialization_default_config(self):
        """Test server initialization with default configuration"""
        config = ServerConfig()
        server = NotebookLMServer(config)

        assert server.config == config
        assert server.client is None
        assert server.server_name == "notebooklm-mcp"

    def test_server_initialization_custom_config(self):
        """Test server initialization with custom configuration"""
        config = ServerConfig(
            server_name="custom-notebooklm",
            default_notebook_id="test-notebook",
            headless=True,
        )
        server = NotebookLMServer(config)

        assert server.config.server_name == "custom-notebooklm"
        assert server.config.default_notebook_id == "test-notebook"
        assert server.config.headless is True

    def test_server_initialization_with_debug(self):
        """Test server initialization with debug mode"""
        config = ServerConfig(debug=True)
        server = NotebookLMServer(config)

        assert server.config.debug is True


class TestNotebookLMServerToolRegistration:
    """Test MCP tool registration and discovery"""

    @pytest.fixture
    def server(self):
        """Server instance for testing"""
        config = ServerConfig()
        return NotebookLMServer(config)

    def test_list_tools_returns_all_tools(self, server):
        """Test that list_tools returns all available tools"""
        tools = server.list_tools()

        expected_tools = [
            "healthcheck",
            "send_chat_message",
            "get_chat_response",
            "get_quick_response",
            "chat_with_notebook",
            "navigate_to_notebook",
            "get_default_notebook",
            "set_default_notebook",
        ]

        tool_names = [tool["name"] for tool in tools]
        for expected_tool in expected_tools:
            assert expected_tool in tool_names

    def test_tool_definitions_have_required_fields(self, server):
        """Test that all tool definitions have required fields"""
        tools = server.list_tools()

        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            # Note: inputSchema might not be required in all MCP versions

    def test_healthcheck_tool_definition(self, server):
        """Test healthcheck tool definition"""
        tools = server.list_tools()
        healthcheck_tool = next((t for t in tools if t["name"] == "healthcheck"), None)

        assert healthcheck_tool is not None
        assert "health" in healthcheck_tool["description"].lower()

    def test_chat_tools_definitions(self, server):
        """Test chat-related tool definitions"""
        tools = server.list_tools()
        tool_names = [tool["name"] for tool in tools]

        chat_tools = ["send_chat_message", "get_chat_response", "chat_with_notebook"]

        for chat_tool in chat_tools:
            assert chat_tool in tool_names


class TestNotebookLMServerClientManagement:
    """Test client lifecycle management"""

    @pytest.fixture
    def server_with_mock_client(self):
        """Server with mocked client"""
        config = ServerConfig()
        server = NotebookLMServer(config)
        server.client = Mock(spec=NotebookLMClient)
        return server

    @pytest.mark.asyncio
    async def test_ensure_client_creates_new_client(self):
        """Test that ensure_client creates a new client when none exists"""
        config = ServerConfig()
        server = NotebookLMServer(config)

        with patch("notebooklm_mcp.server.NotebookLMClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await server._ensure_client()

            assert server.client is not None
            mock_client.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_client_reuses_existing_client(self, server_with_mock_client):
        """Test that ensure_client reuses existing client"""
        existing_client = server_with_mock_client.client

        await server_with_mock_client._ensure_client()

        assert server_with_mock_client.client is existing_client

    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self, server_with_mock_client):
        """Test that cleanup properly closes the client"""
        mock_client = server_with_mock_client.client
        mock_client.close = AsyncMock()

        await server_with_mock_client.cleanup()

        mock_client.close.assert_called_once()
        assert server_with_mock_client.client is None


class TestNotebookLMServerToolExecution:
    """Test tool execution and error handling"""

    @pytest.fixture
    def server_with_mock_client(self):
        """Server with mocked client for tool testing"""
        config = ServerConfig()
        server = NotebookLMServer(config)
        server.client = AsyncMock(spec=NotebookLMClient)
        return server

    @pytest.mark.asyncio
    async def test_healthcheck_tool_success(self, server_with_mock_client):
        """Test successful healthcheck execution"""
        result = await server_with_mock_client.call_tool("healthcheck", {})

        assert "content" in result
        assert len(result["content"]) > 0
        assert "healthy" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_send_chat_message_tool_success(self, server_with_mock_client):
        """Test successful chat message sending"""
        mock_client = server_with_mock_client.client
        mock_client.send_message = AsyncMock()

        args = {"message": "Hello, NotebookLM!"}
        result = await server_with_mock_client.call_tool("send_chat_message", args)

        mock_client.send_message.assert_called_once_with("Hello, NotebookLM!")
        assert "sent" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_get_chat_response_tool_success(self, server_with_mock_client):
        """Test successful chat response retrieval"""
        mock_client = server_with_mock_client.client
        mock_client.get_response = AsyncMock(return_value="AI response")

        result = await server_with_mock_client.call_tool("get_chat_response", {})

        mock_client.get_response.assert_called_once()
        assert "AI response" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_chat_with_notebook_tool_success(self, server_with_mock_client):
        """Test complete chat workflow tool"""
        mock_client = server_with_mock_client.client
        mock_client.send_message = AsyncMock()
        mock_client.get_response = AsyncMock(return_value="Complete response")

        args = {"message": "Test question"}
        result = await server_with_mock_client.call_tool("chat_with_notebook", args)

        mock_client.send_message.assert_called_once_with("Test question")
        mock_client.get_response.assert_called_once()
        assert "Complete response" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_navigate_to_notebook_tool_success(self, server_with_mock_client):
        """Test notebook navigation tool"""
        mock_client = server_with_mock_client.client
        mock_client.navigate_to_notebook = AsyncMock()

        args = {"notebook_id": "test-notebook-123"}
        result = await server_with_mock_client.call_tool("navigate_to_notebook", args)

        mock_client.navigate_to_notebook.assert_called_once_with("test-notebook-123")
        assert "navigated" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_get_default_notebook_tool(self, server_with_mock_client):
        """Test get default notebook tool"""
        server_with_mock_client.config.default_notebook_id = "default-notebook"

        result = await server_with_mock_client.call_tool("get_default_notebook", {})

        assert "default-notebook" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_set_default_notebook_tool(self, server_with_mock_client):
        """Test set default notebook tool"""
        args = {"notebook_id": "new-default-notebook"}
        result = await server_with_mock_client.call_tool("set_default_notebook", args)

        assert (
            server_with_mock_client.config.default_notebook_id == "new-default-notebook"
        )
        assert "set" in result["content"][0]["text"].lower()


class TestNotebookLMServerErrorHandling:
    """Test error handling in tool execution"""

    @pytest.fixture
    def server_with_failing_client(self):
        """Server with client that raises exceptions"""
        config = ServerConfig()
        server = NotebookLMServer(config)
        server.client = AsyncMock(spec=NotebookLMClient)
        return server

    @pytest.mark.asyncio
    async def test_send_message_client_error(self, server_with_failing_client):
        """Test handling of client errors during message sending"""
        mock_client = server_with_failing_client.client
        mock_client.send_message = AsyncMock(side_effect=Exception("Client error"))

        args = {"message": "Test message"}
        result = await server_with_failing_client.call_tool("send_chat_message", args)

        assert "error" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_get_response_client_error(self, server_with_failing_client):
        """Test handling of client errors during response retrieval"""
        mock_client = server_with_failing_client.client
        mock_client.get_response = AsyncMock(side_effect=Exception("Response error"))

        result = await server_with_failing_client.call_tool("get_chat_response", {})

        assert "error" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_navigation_client_error(self, server_with_failing_client):
        """Test handling of client errors during navigation"""
        mock_client = server_with_failing_client.client
        mock_client.navigate_to_notebook = AsyncMock(
            side_effect=Exception("Navigation error")
        )

        args = {"notebook_id": "test-notebook"}
        result = await server_with_failing_client.call_tool(
            "navigate_to_notebook", args
        )

        assert "error" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_unknown_tool_error(self, server_with_failing_client):
        """Test handling of unknown tool calls"""
        with pytest.raises(ValueError):
            await server_with_failing_client.call_tool("unknown_tool", {})

    @pytest.mark.asyncio
    async def test_missing_required_arguments(self, server_with_failing_client):
        """Test handling of missing required arguments"""
        # send_chat_message requires 'message' argument
        result = await server_with_failing_client.call_tool("send_chat_message", {})

        assert "error" in result["content"][0]["text"].lower()


class TestNotebookLMServerConfiguration:
    """Test server configuration and settings"""

    def test_server_config_propagation(self):
        """Test that server config is properly propagated"""
        config = ServerConfig(
            timeout=120, debug=True, default_notebook_id="config-test", headless=False
        )
        server = NotebookLMServer(config)

        assert server.config.timeout == 120
        assert server.config.debug is True
        assert server.config.default_notebook_id == "config-test"
        assert server.config.headless is False

    def test_server_name_configuration(self):
        """Test server name configuration"""
        config = ServerConfig(server_name="custom-mcp-server")
        server = NotebookLMServer(config)

        assert server.config.server_name == "custom-mcp-server"


@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP library not available")
class TestNotebookLMServerMCPIntegration:
    """Test MCP protocol integration (only if MCP is available)"""

    @pytest.mark.asyncio
    async def test_mcp_server_startup(self):
        """Test MCP server startup and shutdown"""
        config = ServerConfig()
        server = NotebookLMServer(config)

        # Test that server can be created without errors
        assert server is not None

        # Test cleanup
        await server.cleanup()

    def test_mcp_tool_format_compliance(self):
        """Test that tools comply with MCP format requirements"""
        config = ServerConfig()
        server = NotebookLMServer(config)
        tools = server.list_tools()

        for tool in tools:
            # Basic MCP tool format validation
            assert isinstance(tool, dict)
            assert "name" in tool
            assert "description" in tool
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)


class TestNotebookLMServerPerformance:
    """Test server performance and concurrency"""

    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self):
        """Test handling of concurrent tool calls"""
        config = ServerConfig()
        server = NotebookLMServer(config)
        server.client = AsyncMock(spec=NotebookLMClient)

        # Simulate concurrent healthcheck calls
        tasks = [server.call_tool("healthcheck", {}) for _ in range(5)]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            assert "content" in result

    @pytest.mark.asyncio
    async def test_tool_call_timeout_handling(self):
        """Test handling of tool call timeouts"""
        config = ServerConfig(timeout=1)  # Very short timeout
        server = NotebookLMServer(config)
        server.client = AsyncMock(spec=NotebookLMClient)

        # Mock a slow operation
        async def slow_operation(*args, **kwargs):
            await asyncio.sleep(2)  # Longer than timeout
            return "Slow response"

        server.client.get_response = slow_operation

        # Tool should handle timeout gracefully
        result = await server.call_tool("get_chat_response", {})
        assert "content" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
