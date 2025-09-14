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

from .server import NotebookLMServer
from .client import NotebookLMClient
from .config import ServerConfig, AuthConfig
from .exceptions import NotebookLMError, AuthenticationError, StreamingError

__all__ = [
    "NotebookLMServer",
    "NotebookLMClient", 
    "ServerConfig",
    "AuthConfig",
    "NotebookLMError",
    "AuthenticationError",
    "StreamingError",
]