"""
NotebookLM FastMCP v2 Server Package

A modern FastMCP v2 server for automating interactions with Google's NotebookLM
platform. Features enhanced type safety, decorator-based tools, and multi-transport
support (STDIO, HTTP, SSE).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("notebooklm-mcp")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"
__author__ = "khengyun"
__email__ = "78076796+khengyun@users.noreply.github.com"
__description__ = (
    "FastMCP v2 server for NotebookLM automation with modern async support"
)

from .client_rpc import NotebookLMRPCClient
from .config import AuthConfig, ServerConfig
from .exceptions import AuthenticationError, NotebookLMError
from .server import NotebookLMFastMCP

__all__ = [
    "NotebookLMFastMCP",
    "NotebookLMRPCClient",
    "ServerConfig",
    "AuthConfig",
    "NotebookLMError",
    "AuthenticationError",
]
