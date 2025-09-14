"""
NotebookLM MCP Server Package

A professional Model Context Protocol (MCP) server for automating interactions
with Google's NotebookLM platform. Features persistent sessions, streaming response
support, and comprehensive automation capabilities.
"""

__version__ = "1.0.0"
__author__ = "NotebookLM MCP Team"
__email__ = "support@notebooklm-mcp.dev"
__description__ = "Professional MCP server for NotebookLM automation"

from .client import NotebookLMClient
from .config import AuthConfig, ServerConfig
from .exceptions import AuthenticationError, NotebookLMError, StreamingError
from .server import NotebookLMServer

__all__ = [
    "NotebookLMServer",
    "NotebookLMClient",
    "ServerConfig",
    "AuthConfig",
    "NotebookLMError",
    "AuthenticationError",
    "StreamingError",
]
