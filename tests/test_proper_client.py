"""Basic sanity checks for the official FastMCP client utilities."""

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


def test_streamable_http_transport_accepts_custom_headers() -> None:
    """Transport construction should preserve caller-provided HTTP headers."""

    transport = StreamableHttpTransport(
        url="http://example.com/mcp",
        headers={"Accept": "application/json"},
    )

    assert transport.url == "http://example.com/mcp"
    assert transport.headers["Accept"] == "application/json"


def test_client_wraps_transport_instance() -> None:
    """The FastMCP client should expose the underlying transport instance."""

    transport = StreamableHttpTransport(url="http://example.com/mcp")
    client = Client(transport)

    assert client.transport is transport
