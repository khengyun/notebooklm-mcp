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

    async def _ensure_client(self) -> None:
        """Ensure NotebookLM client is initialized and authenticated"""
        try:
            if self.client is None:
                self.client = NotebookLMClient(self.config)
                await self.client.start()
                logger.info("✅ NotebookLM client initialized and authenticated")
        except Exception as e:
            logger.error(f"Failed to initialize client: {e}")
            raise NotebookLMError(f"Client initialization failed: {e}")

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
                await self._ensure_client()
                await self.client.send_message(request.message)

                response_data = {"status": "sent", "message": request.message}

                if request.wait_for_response:
                    response = await self.client.get_response()
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
                await self._ensure_client()
                response = await self.client.get_response()

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
                await self._ensure_client()
                response = await self.client.get_response()

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
                await self._ensure_client()

                # Switch notebook if specified
                if request.notebook_id:
                    await self.client.navigate_to_notebook(request.notebook_id)

                # Send message and get response
                await self.client.send_message(request.message)
                response = await self.client.get_response()

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
                await self._ensure_client()
                await self.client.navigate_to_notebook(request.notebook_id)

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

    async def start(
        self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000
    ):
        """Start the FastMCP v2 server with specified transport"""
        try:
            # Initialize client
            await self._ensure_client()

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

    async def stop(self):
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
async def main():
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
