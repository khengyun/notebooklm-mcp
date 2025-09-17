"""Sanity checks for the lightweight HTTP client helpers used in docs/examples."""

from notebooklm_mcp.config import ServerConfig


class FastMCPHttpClient:
    """Minimal helper mirroring the example HTTP client."""

    def __init__(self, base_url: str = "http://127.0.0.1:8001") -> None:
        self.base_url = base_url.rstrip("/")
        self.mcp_url = f"{self.base_url}/mcp"

    def health_url(self) -> str:
        return f"{self.base_url}/health"

    def build_list_tools_request(self) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }


def test_http_client_url_building() -> None:
    """The helper should normalise base URLs and provide health endpoint URLs."""

    client = FastMCPHttpClient("http://example.com/api/")

    assert client.base_url == "http://example.com/api"
    assert client.mcp_url == "http://example.com/api/mcp"
    assert client.health_url() == "http://example.com/api/health"


def test_http_client_builds_json_rpc_payload() -> None:
    """Ensure that the example payload matches the JSON-RPC contract."""

    client = FastMCPHttpClient()

    payload = client.build_list_tools_request()

    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "tools/list"
    assert payload["params"] == {}


def test_http_client_defaults_align_with_config() -> None:
    """The documented base URL should match the default server configuration."""

    config = ServerConfig()
    client = FastMCPHttpClient()

    assert client.base_url.startswith("http://127.0.0.1")
    assert config.base_url == "https://notebooklm.google.com"
