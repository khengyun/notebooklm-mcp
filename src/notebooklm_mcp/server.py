#!/usr/bin/env python3
"""
NotebookLM FastMCP v2 Server
Modern MCP server implementation using FastMCP v2 framework
"""

import asyncio
from contextlib import suppress
from typing import Any, Dict, Optional

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field
from starlette.middleware import Middleware

from .client import NotebookLMClient
from .config import ServerConfig
from .exceptions import NotebookLMError
from .monitoring import (
    health_checker,
    metrics_collector,
    periodic_health_check,
    request_timer,
    setup_monitoring,
)
from .security import APIKeyMiddleware


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
        self._client: Optional[NotebookLMClient] = None
        self._health_task: Optional[asyncio.Task[None]] = None
        self._metrics_started = False
        self._request_semaphore = asyncio.Semaphore(
            max(1, config.max_concurrent_requests)
        )

        # Reset monitoring state for new server instance
        health_checker.client = None
        metrics_collector.update_active_sessions(0)

        # Initialize FastMCP application
        self.app = FastMCP(name="NotebookLM MCP Server v2")

        # Setup tools
        self._setup_tools()

        logger.info(
            f"FastMCP v2 server initialized for notebook: {config.default_notebook_id}"
        )

    @property
    def client(self) -> Optional[NotebookLMClient]:
        return self._client

    @client.setter
    def client(self, value: Optional[NotebookLMClient]) -> None:
        previous = getattr(self, "_client", None)
        if previous is value:
            return

        self._client = value
        health_checker.client = value

        if value is None:
            metrics_collector.update_active_sessions(0)
            return

        metrics_collector.update_active_sessions(1)

        if previous is not None and previous is not value:
            metrics_collector.record_browser_restart()

    async def _ensure_client(self) -> None:
        """Ensure NotebookLM client is initialized and authenticated"""
        try:
            if self.client is None:
                new_client = NotebookLMClient(self.config)
                self.client = new_client

                try:
                    await new_client.start()
                except Exception:
                    # Reset client state on failure so future retries can succeed
                    self.client = None
                    raise

                logger.info("✅ NotebookLM client initialized and authenticated")
        except Exception as e:
            logger.error(f"Failed to initialize client: {e}")
            raise NotebookLMError(f"Client initialization failed: {e}")

    def _start_background_tasks(self) -> None:
        """Start monitoring and health check helpers"""

        if self.config.enable_metrics and not self._metrics_started:
            try:
                setup_monitoring(self.config.metrics_port)
                self._metrics_started = True
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Unable to start Prometheus metrics server on port %s: %s",
                    self.config.metrics_port,
                    exc,
                )

        if not self.config.enable_health_checks:
            return

        if self._health_task is None or self._health_task.done():
            self._health_task = asyncio.create_task(
                periodic_health_check(self.config.health_check_interval)
            )

    async def _cleanup_background_tasks(self) -> None:
        """Cancel background helpers"""

        if self._health_task is None:
            return

        self._health_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._health_task
        self._health_task = None

    @staticmethod
    def _is_local_host(host: str) -> bool:
        return host in {"127.0.0.1", "localhost", "::1"}

    def _setup_tools(self) -> None:
        """Setup FastMCP v2 tools with enhanced error handling and performance"""

        @self.app.tool()
        async def healthcheck() -> Dict[str, Any]:
            """Check if the NotebookLM server is healthy and responsive."""
            async with self._request_semaphore:
                async with request_timer():
                    try:
                        health = await health_checker.check_health()
                        system_info = {
                            "uptime": health.uptime,
                            "memory_usage": health.memory_usage,
                            "cpu_usage": health.cpu_usage,
                            "browser_status": health.browser_status,
                        }
                        metrics = metrics_collector.get_metrics()

                        try:
                            client_present = bool(self.client)
                            getattr(self.client, "_is_authenticated", None)
                        except Exception as client_error:
                            logger.error(
                                "Health check client access failed: %s", client_error
                            )
                            return {
                                "status": "error",
                                "message": "Health check failed: client error",
                                "authenticated": False,
                                "notebook_id": self.config.default_notebook_id,
                                "mode": "headless" if self.config.headless else "gui",
                                "metrics": metrics,
                                "system": system_info,
                            }

                        if not client_present:
                            return {
                                "status": "unhealthy",
                                "message": "Client not initialized",
                                "authenticated": False,
                                "notebook_id": self.config.default_notebook_id,
                                "mode": "headless" if self.config.headless else "gui",
                                "metrics": metrics,
                                "system": system_info,
                            }

                        authenticated = health.authentication_status == "authenticated"
                        browser_ok = not str(health.browser_status).startswith(
                            "unhealthy"
                        )

                        if not authenticated:
                            status = "needs_auth"
                        elif browser_ok:
                            status = "healthy"
                        else:
                            status = "unhealthy"

                        message = {
                            "healthy": "Server is running",
                            "needs_auth": "Authentication required",
                            "unhealthy": "Server requires attention",
                        }.get(status, "Server status unknown")

                        return {
                            "status": status,
                            "message": message,
                            "authenticated": authenticated,
                            "notebook_id": self.config.default_notebook_id,
                            "mode": "headless" if self.config.headless else "gui",
                            "metrics": metrics,
                            "system": system_info,
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
            async with self._request_semaphore:
                async with request_timer():
                    try:
                        await self._ensure_client()
                        if self.client is None:  # pragma: no cover - safety
                            raise NotebookLMError("Client unavailable")

                        await self.client.send_message(request.message)

                        response_data = {"status": "sent", "message": request.message}

                        if request.wait_for_response:
                            response = await self.client.get_response()
                            response_data["response"] = response
                            response_data["status"] = "completed"

                        logger.info(
                            "Message sent successfully: %s...",
                            request.message[:50],
                        )
                        return response_data

                    except Exception as e:
                        logger.error(f"Failed to send message: {e}")
                        raise NotebookLMError(f"Failed to send message: {e}")

        @self.app.tool()
        async def get_chat_response(request: GetResponseRequest) -> Dict[str, Any]:
            """Get the latest response from NotebookLM with streaming support."""
            async with self._request_semaphore:
                async with request_timer():
                    try:
                        await self._ensure_client()
                        if self.client is None:  # pragma: no cover - safety
                            raise NotebookLMError("Client unavailable")

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
            async with self._request_semaphore:
                async with request_timer():
                    try:
                        await self._ensure_client()
                        if self.client is None:  # pragma: no cover - safety
                            raise NotebookLMError("Client unavailable")

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
            async with self._request_semaphore:
                async with request_timer():
                    try:
                        await self._ensure_client()
                        if self.client is None:  # pragma: no cover - safety
                            raise NotebookLMError("Client unavailable")

                        if request.notebook_id:
                            await self.client.navigate_to_notebook(request.notebook_id)

                        await self.client.send_message(request.message)
                        response = await self.client.get_response()

                        logger.info("Chat completed: %s...", request.message[:50])
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
            async with self._request_semaphore:
                async with request_timer():
                    try:
                        await self._ensure_client()
                        if self.client is None:  # pragma: no cover - safety
                            raise NotebookLMError("Client unavailable")

                        await self.client.navigate_to_notebook(request.notebook_id)

                        logger.info("Navigated to notebook: %s", request.notebook_id)
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
            async with self._request_semaphore:
                async with request_timer():
                    return {
                        "status": "success",
                        "notebook_id": self.config.default_notebook_id,
                        "message": "Current default notebook ID",
                    }

        @self.app.tool()
        async def set_default_notebook(request: SetNotebookRequest) -> Dict[str, Any]:
            """Set the default notebook ID."""
            async with self._request_semaphore:
                async with request_timer():
                    try:
                        old_notebook = self.config.default_notebook_id
                        self.config.default_notebook_id = request.notebook_id

                        logger.info(
                            "Default notebook changed: %s → %s",
                            old_notebook,
                            request.notebook_id,
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

    def _build_http_middlewares(self) -> list[Middleware]:
        """Construct HTTP middleware stack based on configuration"""

        middlewares: list[Middleware] = []

        if self.config.require_api_key and self.config.api_keys:
            middlewares.append(
                Middleware(
                    APIKeyMiddleware,
                    api_keys=set(self.config.api_keys),
                    header=self.config.api_key_header,
                    allow_bearer=self.config.allow_bearer_tokens,
                )
            )

        return middlewares

    async def start(
        self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000
    ):
        """Start the FastMCP v2 server with specified transport"""
        try:
            self.config.validate()
            # Initialize client
            await self._ensure_client()

            if transport in {"http", "sse"} and not self._is_local_host(host):
                if not self.config.allow_remote_access:
                    raise NotebookLMError(
                        "Remote access is disabled. Set allow_remote_access=True to bind to non-local hosts."
                    )
                logger.warning(
                    "Remote access enabled for %s transport on host %s", transport, host
                )
                if not self.config.require_api_key:
                    logger.warning(
                        "Remote access enabled without API key protection; consider enabling require_api_key"
                    )
                else:
                    logger.info(
                        "Remote access locked behind API key authentication using header %s",
                        self.config.api_key_header,
                    )

            # Start monitoring helpers
            self._start_background_tasks()

            # Run the FastMCP server with specified transport
            if transport == "http":
                logger.info(f"🌐 Starting HTTP server on http://{host}:{port}/mcp/")
                run_kwargs: Dict[str, Any] = {
                    "transport": "http",
                    "host": host,
                    "port": port,
                }
                middlewares = self._build_http_middlewares()
                if middlewares:
                    run_kwargs["middleware"] = middlewares
                await self.app.run_async(**run_kwargs)
            elif transport == "sse":
                logger.info(f"🌐 Starting SSE server on http://{host}:{port}/")
                run_kwargs = {"transport": "sse", "host": host, "port": port}
                middlewares = self._build_http_middlewares()
                if middlewares:
                    run_kwargs["middleware"] = middlewares
                await self.app.run_async(**run_kwargs)
            else:
                logger.info("📡 Starting STDIO server...")
                await self.app.run_async(transport="stdio")

        except Exception as e:
            logger.error(f"Failed to start FastMCP server: {e}")
            raise NotebookLMError(f"Server startup failed: {e}")
        finally:
            await self._cleanup_background_tasks()

    async def stop(self):
        """Gracefully stop the server"""
        try:
            if self.client:
                await self.client.close()
                logger.info("✅ FastMCP server stopped gracefully")
            await self._cleanup_background_tasks()
            self.client = None
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
