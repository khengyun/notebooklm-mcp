#!/usr/bin/env python3
"""
NotebookLM FastMCP v2 Server
Modern MCP server implementation using FastMCP v2 framework
"""

import asyncio
from typing import Any, Dict, Optional

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

from .client import NotebookLMClient
from .config import ServerConfig
from .exceptions import NotebookLMError


# Pydantic models for type-safe tool parameters
class SendMessageRequest(BaseModel):
    """Request model for sending a message to NotebookLM"""

    message: str = Field(..., description="The message to send to NotebookLM")
    wait_for_response: bool = Field(
        True, description="Whether to wait for response after sending"
    )


class GetResponseRequest(BaseModel):
    """Request model for getting response from NotebookLM"""

    timeout: int = Field(30, description="Timeout in seconds for waiting for response")


class ChatRequest(BaseModel):
    """Request model for complete chat interaction"""

    message: str = Field(..., description="The message to send")
    notebook_id: Optional[str] = Field(
        None, description="Optional notebook ID to switch to"
    )


class NavigateRequest(BaseModel):
    """Request model for navigating to a notebook"""

    notebook_id: str = Field(..., description="The notebook ID to navigate to")


class SetNotebookRequest(BaseModel):
    """Request model for setting default notebook"""

    notebook_id: str = Field(..., description="The notebook ID to set as default")


class CreateNotebookRequest(BaseModel):
    """Request model for creating a notebook"""

    title: str = Field(..., description="Title for the new notebook")


class RenameNotebookRequest(BaseModel):
    """Request model for renaming a notebook"""

    notebook_id: str = Field(..., description="The notebook ID to rename")
    new_title: str = Field(..., description="The new title")


class NotebookIdRequest(BaseModel):
    """Request model for operations that take only a notebook ID"""

    notebook_id: str = Field(..., description="The notebook ID")


class AddSourceUrlRequest(BaseModel):
    """Request model for adding a URL source"""

    notebook_id: str = Field(..., description="The notebook ID")
    url: str = Field(..., description="Web URL or YouTube link to add as a source")


class AddSourceTextRequest(BaseModel):
    """Request model for adding a text source"""

    notebook_id: str = Field(..., description="The notebook ID")
    title: str = Field(..., description="Title for the text source")
    text: str = Field(..., description="The raw text content")


class DeleteSourceRequest(BaseModel):
    """Request model for deleting a source"""

    notebook_id: str = Field(..., description="The notebook ID")
    source_id: str = Field(..., description="The source ID to delete")


class NotebookLMFastMCP:
    """FastMCP v2 server for NotebookLM automation with enhanced error handling"""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.client: Optional[NotebookLMClient] = None

        # Initialize FastMCP application
        self.app = FastMCP(name="NotebookLM MCP Server v2")

        # Setup tools
        self._setup_tools()

        logger.info(
            f"FastMCP v2 server initialized for notebook: {config.default_notebook_id}"
        )

    async def _ensure_client(self) -> NotebookLMClient:
        """Lazily initialize and authenticate the NotebookLM client.

        Called on the first tool invocation (not at server startup) so the MCP
        transport binds immediately and a browser failure degrades a single
        tool call instead of taking down the whole server. Returns the live
        client so callers get a non-optional reference.
        """
        try:
            if self.client is None:
                self.client = self._build_client()
                await self.client.start()
                await self.client.authenticate()
                logger.info("✅ NotebookLM client initialized")
            return self.client
        except Exception as e:
            # Reset so the next call can retry from a clean state.
            self.client = None
            logger.error(f"Failed to initialize client: {e}")
            raise NotebookLMError(f"Client initialization failed: {e}")

    def _build_client(self) -> Any:
        """Construct the client for the configured engine.

        ``rpc`` (default) → notebooklm-py backend with full management.
        ``patchright`` → the browser/DOM engine (chat only). The patchright
        branch goes through the module-level ``NotebookLMClient`` symbol so it
        stays test-injectable.
        """
        engine = getattr(self.config, "engine", "rpc")
        if engine == "patchright":
            return NotebookLMClient(self.config)
        from .client_rpc import NotebookLMRPCClient

        return NotebookLMRPCClient(self.config)

    def _require_management(self) -> Any:
        """Return the client, ensuring the active engine supports management."""
        if self.client is None or not getattr(
            self.client, "supports_management", False
        ):
            raise NotebookLMError(
                "Notebook/source management requires the 'rpc' engine "
                "(set engine='rpc' in your config)."
            )
        return self.client

    def _setup_tools(self) -> None:
        """Setup FastMCP v2 tools with enhanced error handling and performance"""

        @self.app.tool()
        async def healthcheck() -> Dict[str, Any]:
            """Check if the NotebookLM server is healthy and responsive."""
            try:
                if not self.client:
                    return {
                        "status": "unhealthy",
                        "message": "Client not initialized",
                        "authenticated": False,
                    }

                auth_status = getattr(self.client, "_is_authenticated", False)

                return {
                    "status": "healthy" if auth_status else "needs_auth",
                    "message": "Server is running",
                    "authenticated": auth_status,
                    "notebook_id": self.config.default_notebook_id,
                    "mode": "headless" if self.config.headless else "gui",
                }

            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return {
                    "status": "error",
                    "message": f"Health check failed: {e}",
                    "authenticated": False,
                }

        @self.app.tool()
        async def send_chat_message(request: SendMessageRequest) -> Dict[str, Any]:
            """Send a message to NotebookLM chat interface."""
            try:
                client = await self._ensure_client()
                await client.send_message(request.message)

                response_data = {"status": "sent", "message": request.message}

                if request.wait_for_response:
                    response = await client.get_response()
                    response_data["response"] = response
                    response_data["status"] = "completed"

                logger.info(f"Message sent successfully: {request.message[:50]}...")
                return response_data

            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                raise NotebookLMError(f"Failed to send message: {e}")

        @self.app.tool()
        async def get_chat_response(request: GetResponseRequest) -> Dict[str, Any]:
            """Get the latest response from NotebookLM with streaming support."""
            try:
                client = await self._ensure_client()
                response = await client.get_response()

                logger.info("Response retrieved successfully")
                return {
                    "status": "success",
                    "response": response,
                    "message": "Response retrieved successfully",
                }

            except Exception as e:
                logger.error(f"Failed to get response: {e}")
                raise NotebookLMError(f"Failed to get response: {e}")

        @self.app.tool()
        async def get_quick_response() -> Dict[str, Any]:
            """Get current response without waiting for completion."""
            try:
                client = await self._ensure_client()
                response = await client.get_response()

                return {
                    "status": "success",
                    "response": response,
                    "message": "Quick response retrieved",
                }

            except Exception as e:
                logger.error(f"Failed to get quick response: {e}")
                raise NotebookLMError(f"Failed to get quick response: {e}")

        @self.app.tool()
        async def chat_with_notebook(request: ChatRequest) -> Dict[str, Any]:
            """Complete chat interaction: send message and get response."""
            try:
                client = await self._ensure_client()

                # Switch notebook if specified
                if request.notebook_id:
                    await client.navigate_to_notebook(request.notebook_id)

                # Send message and get response
                await client.send_message(request.message)
                response = await client.get_response()

                logger.info(f"Chat completed: {request.message[:50]}...")
                return {
                    "status": "success",
                    "message": request.message,
                    "response": response,
                    "notebook_id": request.notebook_id
                    or self.config.default_notebook_id,
                }

            except Exception as e:
                logger.error(f"Chat interaction failed: {e}")
                raise NotebookLMError(f"Chat interaction failed: {e}")

        @self.app.tool()
        async def navigate_to_notebook(request: NavigateRequest) -> Dict[str, Any]:
            """Navigate to a specific notebook."""
            try:
                client = await self._ensure_client()
                await client.navigate_to_notebook(request.notebook_id)

                logger.info(f"Navigated to notebook: {request.notebook_id}")
                return {
                    "status": "success",
                    "notebook_id": request.notebook_id,
                    "message": f"Successfully navigated to notebook {request.notebook_id}",
                }

            except Exception as e:
                logger.error(f"Navigation failed: {e}")
                raise NotebookLMError(f"Failed to navigate to notebook: {e}")

        @self.app.tool()
        async def get_default_notebook() -> Dict[str, Any]:
            """Get the current default notebook ID."""
            return {
                "status": "success",
                "notebook_id": self.config.default_notebook_id,
                "message": "Current default notebook ID",
            }

        @self.app.tool()
        async def set_default_notebook(request: SetNotebookRequest) -> Dict[str, Any]:
            """Set the default notebook ID."""
            try:
                old_notebook = self.config.default_notebook_id
                self.config.default_notebook_id = request.notebook_id

                logger.info(
                    f"Default notebook changed: {old_notebook} → {request.notebook_id}"
                )
                return {
                    "status": "success",
                    "old_notebook_id": old_notebook,
                    "new_notebook_id": request.notebook_id,
                    "message": f"Default notebook set to {request.notebook_id}",
                }

            except Exception as e:
                logger.error(f"Failed to set default notebook: {e}")
                raise NotebookLMError(f"Failed to set default notebook: {e}")

        # ------------------------------------------------------------------ #
        # Notebook & source management (RPC engine only)
        # ------------------------------------------------------------------ #
        @self.app.tool()
        async def list_notebooks() -> Dict[str, Any]:
            """List all notebooks in the account."""
            try:
                await self._ensure_client()
                client = self._require_management()
                notebooks = await client.list_notebooks()
                return {
                    "status": "success",
                    "count": len(notebooks),
                    "notebooks": notebooks,
                }
            except Exception as e:
                logger.error(f"Failed to list notebooks: {e}")
                raise NotebookLMError(f"Failed to list notebooks: {e}")

        @self.app.tool()
        async def create_notebook(request: CreateNotebookRequest) -> Dict[str, Any]:
            """Create a new notebook with the given title."""
            try:
                await self._ensure_client()
                client = self._require_management()
                notebook = await client.create_notebook(request.title)
                return {"status": "success", "notebook": notebook}
            except Exception as e:
                logger.error(f"Failed to create notebook: {e}")
                raise NotebookLMError(f"Failed to create notebook: {e}")

        @self.app.tool()
        async def rename_notebook(request: RenameNotebookRequest) -> Dict[str, Any]:
            """Rename a notebook."""
            try:
                await self._ensure_client()
                client = self._require_management()
                notebook = await client.rename_notebook(
                    request.notebook_id, request.new_title
                )
                return {"status": "success", "notebook": notebook}
            except Exception as e:
                logger.error(f"Failed to rename notebook: {e}")
                raise NotebookLMError(f"Failed to rename notebook: {e}")

        @self.app.tool()
        async def delete_notebook(request: NotebookIdRequest) -> Dict[str, Any]:
            """Delete a notebook by ID."""
            try:
                await self._ensure_client()
                client = self._require_management()
                await client.delete_notebook(request.notebook_id)
                return {"status": "success", "notebook_id": request.notebook_id}
            except Exception as e:
                logger.error(f"Failed to delete notebook: {e}")
                raise NotebookLMError(f"Failed to delete notebook: {e}")

        @self.app.tool()
        async def get_notebook_summary(request: NotebookIdRequest) -> Dict[str, Any]:
            """Get the AI summary of a notebook."""
            try:
                await self._ensure_client()
                client = self._require_management()
                summary = await client.get_notebook_summary(request.notebook_id)
                return {"status": "success", "summary": summary}
            except Exception as e:
                logger.error(f"Failed to get notebook summary: {e}")
                raise NotebookLMError(f"Failed to get notebook summary: {e}")

        @self.app.tool()
        async def list_sources(request: NotebookIdRequest) -> Dict[str, Any]:
            """List the sources in a notebook."""
            try:
                await self._ensure_client()
                client = self._require_management()
                sources = await client.list_sources(request.notebook_id)
                return {
                    "status": "success",
                    "count": len(sources),
                    "sources": sources,
                }
            except Exception as e:
                logger.error(f"Failed to list sources: {e}")
                raise NotebookLMError(f"Failed to list sources: {e}")

        @self.app.tool()
        async def add_source_url(request: AddSourceUrlRequest) -> Dict[str, Any]:
            """Add a web URL (or YouTube link) as a source to a notebook."""
            try:
                await self._ensure_client()
                client = self._require_management()
                source = await client.add_source_url(request.notebook_id, request.url)
                return {"status": "success", "source": source}
            except Exception as e:
                logger.error(f"Failed to add URL source: {e}")
                raise NotebookLMError(f"Failed to add URL source: {e}")

        @self.app.tool()
        async def add_source_text(request: AddSourceTextRequest) -> Dict[str, Any]:
            """Add raw text as a source to a notebook."""
            try:
                await self._ensure_client()
                client = self._require_management()
                source = await client.add_source_text(
                    request.notebook_id, request.title, request.text
                )
                return {"status": "success", "source": source}
            except Exception as e:
                logger.error(f"Failed to add text source: {e}")
                raise NotebookLMError(f"Failed to add text source: {e}")

        @self.app.tool()
        async def delete_source(request: DeleteSourceRequest) -> Dict[str, Any]:
            """Delete a source from a notebook."""
            try:
                await self._ensure_client()
                client = self._require_management()
                await client.delete_source(request.notebook_id, request.source_id)
                return {
                    "status": "success",
                    "notebook_id": request.notebook_id,
                    "source_id": request.source_id,
                }
            except Exception as e:
                logger.error(f"Failed to delete source: {e}")
                raise NotebookLMError(f"Failed to delete source: {e}")

    async def start(
        self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000
    ) -> None:
        """Start the FastMCP v2 server with specified transport.

        The browser client is initialized lazily on first tool use (see
        ``_ensure_client``), so the transport binds without requiring a working
        browser up front.
        """
        try:
            # Run the FastMCP server with specified transport
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


# Factory function for easy server creation
def create_fastmcp_server(config_file: str) -> NotebookLMFastMCP:
    """Create a FastMCP v2 server from configuration file"""
    from .config import load_config

    config = load_config(config_file)
    return NotebookLMFastMCP(config)


# Main entry point for standalone usage
async def main() -> None:
    """Main entry point for running server standalone"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m notebooklm_mcp.server <config_file>")
        sys.exit(1)

    config_file = sys.argv[1]
    server = create_fastmcp_server(config_file)

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
