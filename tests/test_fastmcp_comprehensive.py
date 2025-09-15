#!/usr/bin/env python3
"""
Comprehensive test suite for FastMCP v2 NotebookLM server
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastmcp.client.transports import StreamableHttpTransport

from notebooklm_mcp.server import NotebookLMFastMCP
from notebooklm_mcp.config import ServerConfig, AuthConfig


@pytest.fixture
def mock_config():
    """Create mock configuration for testing"""
    auth_config = AuthConfig(profile_dir="./test_profile")
    return ServerConfig(
        default_notebook_id="test-notebook-123",
        headless=True,
        timeout=30,
        auth=auth_config,
        debug=True
    )


@pytest.fixture
def mock_client():
    """Create mock NotebookLM client"""
    client = AsyncMock()
    client.start = AsyncMock()
    client.send_message = AsyncMock()
    client.get_response = AsyncMock(return_value="Test response from NotebookLM")
    client.navigate_to_notebook = AsyncMock()
    client.stop = AsyncMock()
    client._is_authenticated = True
    return client


@pytest.fixture
async def fastmcp_server(mock_config, mock_client):
    """Create FastMCP server with mocked client"""
    server = NotebookLMFastMCP(mock_config)
    
    with patch.object(server, '_ensure_client', AsyncMock()):
        server.client = mock_client
        yield server


class TestFastMCPServer:
    """Test FastMCP v2 server functionality"""

    @pytest.mark.asyncio
    async def test_server_initialization(self, mock_config):
        """Test server initializes correctly"""
        server = NotebookLMFastMCP(mock_config)
        
        assert server.config == mock_config
        assert server.client is None
        assert server.app.name == "NotebookLM MCP Server v2"

    @pytest.mark.asyncio
    async def test_ensure_client(self, mock_config):
        """Test client initialization"""
        server = NotebookLMFastMCP(mock_config)
        
        with patch('notebooklm_mcp.server.NotebookLMClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            await server._ensure_client()
            
            assert server.client == mock_client
            mock_client.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_healthcheck_tool(self, fastmcp_server):
        """Test healthcheck tool"""
        # Call the tool directly
        result = await fastmcp_server.app.call_tool("healthcheck", {})
        result = await fastmcp_server.app.call_tool("healthcheck", {})
        
        assert result is not None
        assert "status" in result
        assert "authenticated" in result

    @pytest.mark.asyncio
    async def test_send_message_tool(self, fastmcp_server):
        """Test send_chat_message tool"""
        request_data = {
            "request": {
                "message": "Test message",
                "wait_for_response": False
            }
        }
        
        result = await fastmcp_server.app.call_tool("send_chat_message", request_data)
        
        fastmcp_server.client.send_message.assert_called_once_with("Test message")
        assert result["status"] == "sent"
        assert result["message"] == "Test message"

    @pytest.mark.asyncio
    async def test_get_response_tool(self, fastmcp_server):
        """Test get_chat_response tool"""
        request_data = {"request": {"timeout": 30}}
        
        result = await fastmcp_server.app.call_tool("get_chat_response", request_data)
        
        fastmcp_server.client.get_response.assert_called_once()
        assert result["status"] == "success"
        assert "response" in result

    @pytest.mark.asyncio 
    async def test_chat_with_notebook_tool(self, fastmcp_server):
        """Test complete chat interaction"""
        request_data = {
            "request": {
                "message": "Hello NotebookLM",
                "notebook_id": "test-notebook-456"
            }
        }
        
        result = await fastmcp_server.app.call_tool("chat_with_notebook", request_data)
        
        fastmcp_server.client.navigate_to_notebook.assert_called_once_with("test-notebook-456")
        fastmcp_server.client.send_message.assert_called_once_with("Hello NotebookLM")
        fastmcp_server.client.get_response.assert_called_once()
        
        assert result["status"] == "success"
        assert result["message"] == "Hello NotebookLM"
        assert "response" in result

    @pytest.mark.asyncio
    async def test_navigate_tool(self, fastmcp_server):
        """Test navigate_to_notebook tool"""
        request_data = {"request": {"notebook_id": "new-notebook-789"}}
        
        result = await fastmcp_server.app.call_tool("navigate_to_notebook", request_data)
        
        fastmcp_server.client.navigate_to_notebook.assert_called_once_with("new-notebook-789")
        assert result["status"] == "success"
        assert result["notebook_id"] == "new-notebook-789"

    @pytest.mark.asyncio
    async def test_get_default_notebook(self, fastmcp_server):
        """Test get_default_notebook tool"""
        result = await fastmcp_server.app.call_tool("get_default_notebook", {})
        
        assert result["status"] == "success"
        assert result["notebook_id"] == "test-notebook-123"

    @pytest.mark.asyncio
    async def test_set_default_notebook(self, fastmcp_server):
        """Test set_default_notebook tool"""
        request_data = {"request": {"notebook_id": "updated-notebook-999"}}
        
        result = await fastmcp_server.app.call_tool("set_default_notebook", request_data)
        
        assert result["status"] == "success"
        assert result["new_notebook_id"] == "updated-notebook-999"
        assert fastmcp_server.config.default_notebook_id == "updated-notebook-999"


class TestFastMCPHTTPClient:
    """Test FastMCP v2 HTTP client integration"""

    @pytest.mark.asyncio
    async def test_http_client_connection(self):
        """Test HTTP client can connect to server"""
        # This would require a running HTTP server
        # For now, test the transport creation
        transport = StreamableHttpTransport(
            url="http://localhost:8001/mcp",
            headers={"Accept": "application/json, text/event-stream"}
        )
        
        assert transport.url == "http://localhost:8001/mcp"
        assert "Accept" in transport.headers

    @pytest.mark.asyncio
    async def test_http_tool_listing(self):
        """Test listing tools via HTTP"""
        # Mock HTTP response
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {"name": "healthcheck", "description": "Health check"},
                        {"name": "send_chat_message", "description": "Send message"}
                    ]
                }
            }
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            # Test would go here - requires actual HTTP client implementation
            assert True  # Placeholder


class TestErrorHandling:
    """Test error handling in FastMCP v2 server"""

    @pytest.mark.asyncio
    async def test_client_initialization_error(self, mock_config):
        """Test handling of client initialization errors"""
        server = NotebookLMFastMCP(mock_config)
        
        with patch('notebooklm_mcp.server.NotebookLMClient') as mock_client_class:
            mock_client_class.side_effect = Exception("Client init failed")
            
            with pytest.raises(Exception):
                await server._ensure_client()

    @pytest.mark.asyncio
    async def test_tool_error_handling(self, fastmcp_server):
        """Test tool error handling"""
        # Make client method raise an exception
        fastmcp_server.client.send_message.side_effect = Exception("Send failed")
        
        request_data = {
            "request": {
                "message": "Test message",
                "wait_for_response": False
            }
        }
        
        with pytest.raises(Exception):
            await fastmcp_server.app.call_tool("send_chat_message", request_data)


class TestTransports:
    """Test different transport modes"""

    @pytest.mark.asyncio
    async def test_stdio_transport(self, fastmcp_server):
        """Test STDIO transport configuration"""
        # Mock the FastMCP run_async method
        with patch.object(fastmcp_server.app, 'run_async', AsyncMock()) as mock_run:
            await fastmcp_server.start(transport="stdio")
            mock_run.assert_called_once_with(transport="stdio")

    @pytest.mark.asyncio
    async def test_http_transport(self, fastmcp_server):
        """Test HTTP transport configuration"""
        with patch.object(fastmcp_server.app, 'run_async', AsyncMock()) as mock_run:
            await fastmcp_server.start(transport="http", host="0.0.0.0", port=9000)
            mock_run.assert_called_once_with(transport="http", host="0.0.0.0", port=9000)

    @pytest.mark.asyncio
    async def test_sse_transport(self, fastmcp_server):
        """Test SSE transport configuration"""
        with patch.object(fastmcp_server.app, 'run_async', AsyncMock()) as mock_run:
            await fastmcp_server.start(transport="sse", host="127.0.0.1", port=8002)
            mock_run.assert_called_once_with(transport="sse", host="127.0.0.1", port=8002)


class TestTypeValidation:
    """Test Pydantic type validation"""

    @pytest.mark.asyncio
    async def test_send_message_validation(self, fastmcp_server):
        """Test send message parameter validation"""
        # Test with invalid parameters
        invalid_request = {"invalid": "data"}
        
        with pytest.raises(Exception):  # Should raise validation error
            await fastmcp_server.app.call_tool("send_chat_message", invalid_request)

    @pytest.mark.asyncio
    async def test_navigate_validation(self, fastmcp_server):
        """Test navigation parameter validation"""
        # Test missing required parameter
        invalid_request = {"request": {}}  # Missing notebook_id
        
        with pytest.raises(Exception):  # Should raise validation error
            await fastmcp_server.app.call_tool("navigate_to_notebook", invalid_request)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])