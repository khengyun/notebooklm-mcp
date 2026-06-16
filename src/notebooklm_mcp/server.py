#!/usr/bin/env python3
"""
NotebookLM FastMCP v2 Server
Modern MCP server implementation using FastMCP v2 framework
"""

import asyncio
import functools
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

from .client_rpc import NotebookLMRPCClient
from .config import ServerConfig
from .exceptions import NotebookLMError

_T = TypeVar("_T")


class SourceRef(BaseModel):
    """A reference to a source living in some notebook (for copy/merge)."""

    notebook_id: str = Field(..., description="Notebook that holds the source")
    source_id: str = Field(..., description="ID of the source to copy")


def _tool(
    error_prefix: str,
) -> Callable[[Callable[..., Awaitable[_T]]], Callable[..., Awaitable[_T]]]:
    """Wrap a tool coroutine so any exception is logged and re-raised as a
    :class:`NotebookLMError` with a stable ``"<error_prefix>: <exc>"`` message.

    This collapses the repeated ``try/except Exception`` boilerplate that each
    tool used to carry. The raised message text is part of the public contract
    (tests match on it), so it is built solely from ``error_prefix``.
    """

    def decorator(
        func: Callable[..., Awaitable[_T]],
    ) -> Callable[..., Awaitable[_T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> _T:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{error_prefix}: {e}")
                raise NotebookLMError(f"{error_prefix}: {e}")

        return wrapper

    return decorator


class NotebookLMFastMCP:
    """FastMCP v2 server for NotebookLM automation with enhanced error handling"""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.client: Optional[NotebookLMRPCClient] = None
        self.app = FastMCP(name="NotebookLM MCP Server v2")
        self._setup_tools()
        logger.info(
            f"FastMCP v2 server initialized for notebook: {config.default_notebook_id}"
        )

    async def _ensure_client(self) -> NotebookLMRPCClient:
        """Lazily initialize and authenticate the NotebookLM RPC client.

        Called on the first tool invocation (not at server startup) so the MCP
        transport binds immediately and a session/auth failure degrades a single
        tool call instead of taking down the whole server. Returns the live
        client so callers get a non-optional reference.
        """
        try:
            if self.client is None:
                self.client = NotebookLMRPCClient(self.config)
                await self.client.start()
                await self.client.authenticate()
                logger.info("✅ NotebookLM client initialized")
            return self.client
        except Exception as e:
            # Reset so the next call can retry from a clean state.
            self.client = None
            logger.error(f"Failed to initialize client: {e}")
            raise NotebookLMError(f"Client initialization failed: {e}")

    def _setup_tools(self) -> None:
        """Register the FastMCP tools. Parameters are plain typed arguments, so
        FastMCP generates a flat input schema for each tool."""

        # ------------------------------------------------------------------ #
        # Chat
        # ------------------------------------------------------------------ #
        @self.app.tool()
        async def healthcheck() -> Dict[str, Any]:
            """Check if the NotebookLM server is healthy and responsive."""
            if self.client is None:
                return {
                    "status": "unhealthy",
                    "message": "Client not initialized",
                    "authenticated": False,
                }
            authed = self.client.is_authenticated
            return {
                "status": "healthy" if authed else "needs_auth",
                "message": "Server is running",
                "authenticated": authed,
                "notebook_id": self.config.default_notebook_id,
                "mode": "headless" if self.config.headless else "gui",
            }

        @self.app.tool()
        @_tool("Failed to send message")
        async def send_chat_message(
            message: str, wait_for_response: bool = True
        ) -> Dict[str, Any]:
            """Send a message to NotebookLM chat interface."""
            client = await self._ensure_client()
            await client.send_message(message)
            data: Dict[str, Any] = {"status": "sent", "message": message}
            if wait_for_response:
                data["response"] = await client.get_response()
                data["status"] = "completed"
            logger.info(f"Message sent: {message[:50]}...")
            return data

        @self.app.tool()
        @_tool("Failed to get response")
        async def get_chat_response() -> Dict[str, Any]:
            """Get the latest response from NotebookLM."""
            client = await self._ensure_client()
            return {
                "status": "success",
                "response": await client.get_response(),
                "message": "Response retrieved successfully",
            }

        @self.app.tool()
        @_tool("Chat interaction failed")
        async def chat_with_notebook(
            message: str, notebook_id: Optional[str] = None
        ) -> Dict[str, Any]:
            """Complete chat interaction: send message and get response."""
            client = await self._ensure_client()
            if notebook_id:
                await client.navigate_to_notebook(notebook_id)
            await client.send_message(message)
            response = await client.get_response()
            logger.info(f"Chat completed: {message[:50]}...")
            return {
                "status": "success",
                "message": message,
                "response": response,
                "notebook_id": notebook_id or self.config.default_notebook_id,
            }

        @self.app.tool()
        @_tool("Failed to navigate to notebook")
        async def navigate_to_notebook(notebook_id: str) -> Dict[str, Any]:
            """Navigate to a specific notebook."""
            client = await self._ensure_client()
            await client.navigate_to_notebook(notebook_id)
            logger.info(f"Navigated to notebook: {notebook_id}")
            return {
                "status": "success",
                "notebook_id": notebook_id,
                "message": f"Successfully navigated to notebook {notebook_id}",
            }

        @self.app.tool()
        async def get_default_notebook() -> Dict[str, Any]:
            """Get the current default notebook ID."""
            return {
                "status": "success",
                "notebook_id": self.config.default_notebook_id,
                "message": "Current default notebook ID",
            }

        @self.app.tool()
        @_tool("Failed to set default notebook")
        async def set_default_notebook(notebook_id: str) -> Dict[str, Any]:
            """Set the default notebook ID."""
            old_notebook = self.config.default_notebook_id
            self.config.default_notebook_id = notebook_id
            logger.info(f"Default notebook changed: {old_notebook} → {notebook_id}")
            return {
                "status": "success",
                "old_notebook_id": old_notebook,
                "new_notebook_id": notebook_id,
                "message": f"Default notebook set to {notebook_id}",
            }

        # ------------------------------------------------------------------ #
        # Notebook & source management
        # ------------------------------------------------------------------ #
        @self.app.tool()
        @_tool("Failed to list notebooks")
        async def list_notebooks() -> Dict[str, Any]:
            """List all notebooks in the account."""
            client = await self._ensure_client()
            notebooks = await client.list_notebooks()
            return {
                "status": "success",
                "count": len(notebooks),
                "notebooks": notebooks,
            }

        @self.app.tool()
        @_tool("Failed to create notebook")
        async def create_notebook(title: str) -> Dict[str, Any]:
            """Create a new notebook with the given title."""
            client = await self._ensure_client()
            return {
                "status": "success",
                "notebook": await client.create_notebook(title),
            }

        @self.app.tool()
        @_tool("Failed to rename notebook")
        async def rename_notebook(notebook_id: str, new_title: str) -> Dict[str, Any]:
            """Rename a notebook."""
            client = await self._ensure_client()
            notebook = await client.rename_notebook(notebook_id, new_title)
            return {"status": "success", "notebook": notebook}

        @self.app.tool()
        @_tool("Failed to delete notebook")
        async def delete_notebook(notebook_id: str) -> Dict[str, Any]:
            """Delete a notebook by ID."""
            client = await self._ensure_client()
            await client.delete_notebook(notebook_id)
            return {"status": "success", "notebook_id": notebook_id}

        @self.app.tool()
        @_tool("Failed to get notebook summary")
        async def get_notebook_summary(notebook_id: str) -> Dict[str, Any]:
            """Get the AI summary of a notebook."""
            client = await self._ensure_client()
            summary = await client.get_notebook_summary(notebook_id)
            return {"status": "success", "summary": summary}

        @self.app.tool()
        @_tool("Failed to list sources")
        async def list_sources(notebook_id: str) -> Dict[str, Any]:
            """List the sources in a notebook."""
            client = await self._ensure_client()
            sources = await client.list_sources(notebook_id)
            return {"status": "success", "count": len(sources), "sources": sources}

        @self.app.tool()
        @_tool("Failed to add URL source")
        async def add_source_url(notebook_id: str, url: str) -> Dict[str, Any]:
            """Add a web URL (or YouTube link) as a source to a notebook."""
            client = await self._ensure_client()
            source = await client.add_source_url(notebook_id, url)
            return {"status": "success", "source": source}

        @self.app.tool()
        @_tool("Failed to add text source")
        async def add_source_text(
            notebook_id: str, title: str, text: str
        ) -> Dict[str, Any]:
            """Add raw text as a source to a notebook."""
            client = await self._ensure_client()
            source = await client.add_source_text(notebook_id, title, text)
            return {"status": "success", "source": source}

        @self.app.tool()
        @_tool("Failed to delete source")
        async def delete_source(notebook_id: str, source_id: str) -> Dict[str, Any]:
            """Delete a source from a notebook."""
            client = await self._ensure_client()
            await client.delete_source(notebook_id, source_id)
            return {
                "status": "success",
                "notebook_id": notebook_id,
                "source_id": source_id,
            }

        @self.app.tool()
        @_tool("Failed to copy source")
        async def copy_source(
            source_notebook_id: str, source_id: str, target_notebook_id: str
        ) -> Dict[str, Any]:
            """Copy a single source from one notebook into another."""
            client = await self._ensure_client()
            source = await client.copy_source(
                source_notebook_id, source_id, target_notebook_id
            )
            return {"status": "success", "source": source}

        @self.app.tool()
        @_tool("Failed to create notebook from sources")
        async def create_notebook_from_sources(
            title: str, sources: List[SourceRef]
        ) -> Dict[str, Any]:
            """Create a new notebook composed of sources copied from other
            notebooks (merge sources across notebooks).

            Each item in ``sources`` is ``{notebook_id, source_id}``. Sources are
            copied by URL when available, else by re-adding their extracted text.
            Add more sources afterwards with ``add_source_url``/``add_source_text``.
            """
            client = await self._ensure_client()
            refs = [s.model_dump() for s in sources]
            result = await client.create_notebook_from_sources(title, refs)
            return {"status": "success", **result}

    async def start(
        self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000
    ) -> None:
        """Start the FastMCP v2 server with the given transport.

        The client is initialized lazily on first tool use (see
        ``_ensure_client``), so the transport binds without requiring a session.
        """
        try:
            if transport == "http":
                logger.info(f"🌐 Starting HTTP server on http://{host}:{port}/mcp/")
                await self.app.run_async(transport="http", host=host, port=port)
            elif transport == "sse":
                logger.info(f"🌐 Starting SSE server on http://{host}:{port}/")
                await self.app.run_async(transport="sse", host=host, port=port)
            else:
                logger.info("📡 Starting STDIO server...")
                await self.app.run_async(transport="stdio")
        except Exception as e:
            logger.error(f"Failed to start FastMCP server: {e}")
            raise NotebookLMError(f"Server startup failed: {e}")

    async def stop(self) -> None:
        """Gracefully stop the server"""
        try:
            if self.client:
                await self.client.close()
                logger.info("✅ FastMCP server stopped gracefully")
        except Exception as e:
            logger.error(f"Error during server shutdown: {e}")


def create_fastmcp_server(config_file: str) -> NotebookLMFastMCP:
    """Create a FastMCP v2 server from a configuration file."""
    from .config import load_config

    return NotebookLMFastMCP(load_config(config_file))


async def main() -> None:
    """Main entry point for running the server standalone."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m notebooklm_mcp.server <config_file>")
        sys.exit(1)

    server = create_fastmcp_server(sys.argv[1])
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
