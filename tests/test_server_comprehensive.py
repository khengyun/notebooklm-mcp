"""Targeted tests for :mod:`notebooklm_mcp.server`."""

from unittest.mock import AsyncMock, patch

import pytest

from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.server import NotebookLMFastMCP, create_fastmcp_server


@pytest.fixture
def server_config() -> ServerConfig:
    return ServerConfig(default_notebook_id="fixture-notebook", headless=True)


@pytest.fixture
def fastmcp_server(server_config: ServerConfig) -> NotebookLMFastMCP:
    return NotebookLMFastMCP(server_config)


@pytest.mark.asyncio
async def test_ensure_client_initialises_notebook_client(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    """`_ensure_client` should construct and start a NotebookLM client when missing."""

    with patch("notebooklm_mcp.server.NotebookLMClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        await fastmcp_server._ensure_client()

    mock_client_cls.assert_called_once_with(fastmcp_server.config)
    mock_client.start.assert_awaited_once()
    assert fastmcp_server.client is mock_client


@pytest.mark.asyncio
async def test_start_invokes_fastmcp_run_async(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    """Starting the server should call the underlying FastMCP run method."""

    fastmcp_server.client = AsyncMock()
    fastmcp_server._ensure_client = AsyncMock()

    with patch.object(fastmcp_server.app, "run_async", AsyncMock()) as mock_run:
        await fastmcp_server.start(transport="http", host="0.0.0.0", port=9000)

    fastmcp_server._ensure_client.assert_awaited_once()
    mock_run.assert_awaited_once_with(transport="http", host="0.0.0.0", port=9000)


@pytest.mark.asyncio
async def test_stop_closes_existing_client(fastmcp_server: NotebookLMFastMCP) -> None:
    """Calling `stop` should close the active client if present."""

    mock_client = AsyncMock()
    fastmcp_server.client = mock_client

    await fastmcp_server.stop()

    mock_client.close.assert_awaited_once()
    assert fastmcp_server.client is mock_client  # The server keeps reference for re-use


def test_create_fastmcp_server_uses_config_loader(server_config: ServerConfig) -> None:
    """Factory helper should delegate to :func:`load_config` and construct the server."""

    with patch(
        "notebooklm_mcp.config.load_config", return_value=server_config
    ) as mock_load:
        server = create_fastmcp_server("config.json")

    mock_load.assert_called_once_with("config.json")
    assert isinstance(server, NotebookLMFastMCP)
    assert server.config is server_config
