#!/usr/bin/env python3
"""
NotebookLM MCP Server
Professional MCP server for NotebookLM automation with streaming support
"""

import asyncio
import sys
from typing import Any, Dict, List, Optional

from loguru import logger

# MCP Python SDK
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError:
    logger.error("MCP library required. Install with: pip install mcp")
    sys.exit(1)

from .client import NotebookLMClient
from .config import ServerConfig, load_config
from .exceptions import NotebookLMError
from .monitoring import health_checker, request_timer


class NotebookLMServer:
    """Professional MCP server for NotebookLM automation"""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.client: Optional[NotebookLMClient] = None
        self.server = Server("notebooklm-mcp")
        self._setup_tools()

    def _setup_tools(self):
        """Register MCP tools"""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(name="healthcheck", description="Check server health status"),
                Tool(
                    name="send_chat_message",
                    description="Send a message to NotebookLM chat",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Message to send",
                            }
                        },
                        "required": ["message"],
                    },
                ),
                Tool(
                    name="get_chat_response",
                    description="Get response from NotebookLM with streaming support",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "wait_for_completion": {
                                "type": "boolean",
                                "description": "Wait for streaming to complete",
                                "default": True,
                            },
                            "max_wait": {
                                "type": "integer",
                                "description": "Maximum wait time in seconds",
                                "default": 60,
                            },
                        },
                    },
                ),
                Tool(
                    name="get_quick_response",
                    description="Get current response without waiting for completion",
                ),
                Tool(
                    name="chat_with_notebook",
                    description="Send message and get complete response",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Message to send",
                            },
                            "max_wait": {
                                "type": "integer",
                                "description": "Maximum wait time in seconds",
                                "default": 60,
                            },
                        },
                        "required": ["message"],
                    },
                ),
                Tool(
                    name="navigate_to_notebook",
                    description="Navigate to specific notebook",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "notebook_id": {
                                "type": "string",
                                "description": "Notebook ID",
                            }
                        },
                        "required": ["notebook_id"],
                    },
                ),
                Tool(
                    name="get_default_notebook",
                    description="Get current default notebook ID",
                ),
                Tool(
                    name="set_default_notebook",
                    description="Set default notebook ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "notebook_id": {
                                "type": "string",
                                "description": "Notebook ID",
                            }
                        },
                        "required": ["notebook_id"],
                    },
                ),
                Tool(name="shutdown", description="Shutdown the server gracefully"),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            try:
                async with request_timer():
                    result = await self._execute_tool(name, arguments)
                    return [TextContent(type="text", text=str(result))]
            except Exception as e:
                logger.error(f"Tool {name} failed: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute individual tools"""

        # Ensure client is ready
        if not self.client and name != "healthcheck":
            await self._ensure_client()

        if name == "healthcheck":
            health = await health_checker.check_health()
            return f"Server healthy: {health.healthy}, Uptime: {health.uptime:.1f}s"

        elif name == "send_chat_message":
            message = arguments.get("message", "")
            await self.client.send_message(message)
            return "Message sent successfully"

        elif name == "get_chat_response":
            wait_for_completion = arguments.get("wait_for_completion", True)
            max_wait = arguments.get("max_wait", 60)
            response = await self.client.get_response(wait_for_completion, max_wait)
            return response

        elif name == "get_quick_response":
            response = await self.client.get_response(wait_for_completion=False)
            return response

        elif name == "chat_with_notebook":
            message = arguments.get("message", "")
            max_wait = arguments.get("max_wait", 60)

            # Send message
            await self.client.send_message(message)
            # Wait for complete response
            response = await self.client.get_response(
                wait_for_completion=True, max_wait=max_wait
            )
            return response

        elif name == "navigate_to_notebook":
            notebook_id = arguments.get("notebook_id", "")
            result_url = await self.client.navigate_to_notebook(notebook_id)
            return f"Navigated to: {result_url}"

        elif name == "get_default_notebook":
            return self.config.default_notebook_id or "No default notebook set"

        elif name == "set_default_notebook":
            notebook_id = arguments.get("notebook_id", "")
            self.config.default_notebook_id = notebook_id
            return f"Default notebook set to: {notebook_id}"

        elif name == "shutdown":
            asyncio.create_task(self._shutdown())
            return "Server shutting down..."

        else:
            raise NotebookLMError(f"Unknown tool: {name}")

    async def _ensure_client(self):
        """Ensure client is initialized and authenticated"""
        if not self.client:
            self.client = NotebookLMClient(self.config)
            health_checker.client = self.client

            logger.info("Starting browser client...")
            await self.client.start()

            logger.info("Authenticating...")
            auth_success = await self.client.authenticate()

            if not auth_success and not self.config.headless:
                logger.warning(
                    "Authentication required - browser will stay open for manual login"
                )

    async def _shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down server...")
        if self.client:
            await self.client.close()
        # Give time for shutdown message to be sent
        await asyncio.sleep(1)
        sys.exit(0)

    async def run(self):
        """Run the MCP server"""
        try:
            logger.info("Starting NotebookLM MCP Server...")

            # Initialize client if needed
            if self.config.default_notebook_id:
                await self._ensure_client()

            # Start MCP server over STDIO
            async with stdio_server() as (reader, writer):
                await self.server.run(reader, writer, {})

        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
        finally:
            if self.client:
                await self.client.close()


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="NotebookLM MCP Server")
    parser.add_argument("--config", "-c", help="Configuration file path")
    parser.add_argument("--notebook", "-n", help="Default notebook ID")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Override with CLI arguments
    if args.notebook:
        config.default_notebook_id = args.notebook
    if args.headless:
        config.headless = True
    if args.debug:
        config.debug = True

    # Validate configuration
    config.validate()

    # Setup logging
    from .monitoring import setup_logging

    setup_logging(config.debug)

    # Start server
    server = NotebookLMServer(config)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
