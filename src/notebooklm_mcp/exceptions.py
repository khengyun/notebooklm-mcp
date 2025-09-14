"""
Custom exceptions for NotebookLM MCP Server
"""


class NotebookLMError(Exception):
    """Base exception for all NotebookLM operations"""

    pass


class AuthenticationError(NotebookLMError):
    """Raised when authentication fails"""

    pass


class StreamingError(NotebookLMError):
    """Raised when streaming response handling fails"""

    pass


class NavigationError(NotebookLMError):
    """Raised when browser navigation fails"""

    pass


class ChatError(NotebookLMError):
    """Raised when chat operations fail"""

    pass


class ConfigurationError(NotebookLMError):
    """Raised when configuration is invalid"""

    pass
