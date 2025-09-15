"""
NotebookLM FastMCP v2 Server Package

A modern FastMCP v2 server for automating interactions with Google's NotebookLM 
platform. Features enhanced type safety, decorator-based tools, and multi-transport 
support (STDIO, HTTP, SSE).
"""

__version__ = "2.0.0"
__author__ = "NotebookLM MCP Team"
__email__ = "support@notebooklm-mcp.dev"
__description__ = "FastMCP v2 server for NotebookLM automation with modern async support"

from .client import NotebookLMClient
from .config import AuthConfig, ServerConfig
from .exceptions import AuthenticationError, NotebookLMError, StreamingError
from .server import NotebookLMFastMCP

__all__ = [
    "NotebookLMFastMCP",
    "NotebookLMClient", 
    "ServerConfig",
    "AuthConfig",
    "NotebookLMError",
    "AuthenticationError",
    "StreamingError",
]
