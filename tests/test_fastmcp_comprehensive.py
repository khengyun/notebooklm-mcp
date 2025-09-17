"""Focused tests for the FastMCP server integration layer."""

from unittest.mock import AsyncMock, patch

import pytest

from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.server import (
    NotebookLMFastMCP,
    SendMessageRequest,
    SetNotebookRequest,
)


@pytest.fixture
def fastmcp_server() -> NotebookLMFastMCP:
    """Provide a FastMCP server instance with a lightweight configuration."""

    return NotebookLMFastMCP(ServerConfig(default_notebook_id="initial-notebook"))


@pytest.mark.asyncio
async def test_fastmcp_registers_core_tools(fastmcp_server: NotebookLMFastMCP) -> None:
    """The FastMCP instance should expose the core NotebookLM tools."""

    tool_names = set(fastmcp_server.app._tool_manager._tools.keys())

    expected = {
        "healthcheck",
        "send_chat_message",
        "get_chat_response",
        "get_quick_response",
        "chat_with_notebook",
        "navigate_to_notebook",
        "get_default_notebook",
        "set_default_notebook",
    }

    assert expected.issubset(tool_names)


@pytest.mark.asyncio
async def test_healthcheck_reports_uninitialised_client(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    """Healthcheck should indicate that the client is not ready before start."""

    tool = fastmcp_server.app._tool_manager._tools["healthcheck"]

    result = await tool.fn()

    assert result["status"] == "unhealthy"
    assert result["authenticated"] is False


@pytest.mark.asyncio
async def test_send_chat_message_tool_uses_client(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    """The send_chat_message tool should delegate to the NotebookLM client."""

    with patch.object(fastmcp_server, "_ensure_client", AsyncMock()) as mock_ensure:
        mock_client = AsyncMock()
        mock_client.get_response.return_value = "response-text"
        fastmcp_server.client = mock_client

        tool = fastmcp_server.app._tool_manager._tools["send_chat_message"]
        request = SendMessageRequest(message="hello", wait_for_response=True)

        result = await tool.fn(request)

    mock_ensure.assert_awaited()
    mock_client.send_message.assert_awaited_once_with("hello")
    mock_client.get_response.assert_awaited_once()
    assert result["status"] == "completed"
    assert result["response"] == "response-text"


@pytest.mark.asyncio
async def test_set_default_notebook_updates_configuration(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    """The set_default_notebook tool should update the stored config."""

    tool = fastmcp_server.app._tool_manager._tools["set_default_notebook"]
    request = SetNotebookRequest(notebook_id="updated-notebook")

    result = await tool.fn(request)

    assert fastmcp_server.config.default_notebook_id == "updated-notebook"
    assert result["new_notebook_id"] == "updated-notebook"
