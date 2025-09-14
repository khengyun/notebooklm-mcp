#!/usr/bin/env python3
"""
NotebookLM MCP Server
Professional MCP server for NotebookLM automation with streaming support
"""

import asyncio
import sys
from typing import Optional, List, Dict, Any
from loguru import logger

# MCP Python SDK
try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    from mcp.server.stdio import stdio_server
except ImportError as e:
    logger.error("MCP library required. Install with: pip install mcp")
    sys.exit(1)

from .config import ServerConfig, load_config
from .client import NotebookLMClient
from .exceptions import NotebookLMError
from .monitoring import metrics_collector, health_checker, request_timer


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
                Tool(
                    name="healthcheck",
                    description="Check server health status"
                ),
                Tool(
                    name="send_chat_message", 
                    description="Send a message to NotebookLM chat",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "Message to send"}
                        },
                        "required": ["message"]
                    }
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
                                "default": True
                            },
                            "max_wait": {
                                "type": "integer",
                                "description": "Maximum wait time in seconds", 
                                "default": 60
                            }
                        }
                    }
                ),
                Tool(
                    name="get_quick_response",
                    description="Get current response without waiting for completion"
                ),
                Tool(
                    name="chat_with_notebook",
                    description="Send message and get complete response",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "Message to send"},
                            "max_wait": {
                                "type": "integer", 
                                "description": "Maximum wait time in seconds",
                                "default": 60
                            }
                        },
                        "required": ["message"]
                    }
                ),
                Tool(
                    name="navigate_to_notebook",
                    description="Navigate to specific notebook",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "notebook_id": {"type": "string", "description": "Notebook ID"}
                        },
                        "required": ["notebook_id"]
                    }
                ),
                Tool(
                    name="get_default_notebook",
                    description="Get current default notebook ID"
                ),
                Tool(
                    name="set_default_notebook", 
                    description="Set default notebook ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "notebook_id": {"type": "string", "description": "Notebook ID"}
                        },
                        "required": ["notebook_id"]
                    }
                ),
                Tool(
                    name="shutdown",
                    description="Shutdown the server gracefully"
                )
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
            response = await self.client.get_response(wait_for_completion=True, max_wait=max_wait)
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
                logger.warning("Authentication required - browser will stay open for manual login")
    
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
    headless: bool
    timeout: int
    debug: bool
    default_notebook_id: Optional[str] = None


class SeleniumManager:
    def __init__(self, cfg: ServerConfig):
        self.cfg = cfg
        self.driver: Optional[webdriver.Chrome] = None
        self.current_notebook_id: Optional[str] = cfg.default_notebook_id
        self.profile_dir = "./chrome_profile_notebooklm"  # Persistent profile
        
    def start(self) -> None:
        """Start browser with persistent profile for auto-login"""
        if USE_UNDETECTED:
            logger.info("Using undetected-chromedriver with persistent session")
            
            # Create persistent profile directory
            profile_path = Path(self.profile_dir).absolute()
            profile_path.mkdir(exist_ok=True)
            
            options = uc.ChromeOptions()
            options.add_argument(f"--user-data-dir={profile_path}")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-extensions")
            
            if self.cfg.headless:
                options.add_argument("--headless=new")
                
            self.driver = uc.Chrome(options=options, version_main=None)
        else:
            # Fallback to regular Selenium với anti-detection
            logger.warning("undetected-chromedriver not available, using regular Selenium")
            opts = ChromeOptions()
            
            # Anti-detection options
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-web-security")
            opts.add_argument("--disable-features=VizDisplayCompositor")
            
            # Bypass automation detection
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option('useAutomationExtension', False)
            
            # Set user agent
            opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            opts.add_argument("--window-size=1920,1080")
            
            if self.cfg.headless:
                opts.add_argument("--headless=new")
                
            self.driver = webdriver.Chrome(options=opts)
            
            # Remove automation indicators
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        self.driver.set_page_load_timeout(self.cfg.timeout)

    def stop(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _load_cookies(self) -> int:
        if not self.cfg.cookies_path or not os.path.exists(self.cfg.cookies_path):
            logger.warning("No cookies file found or provided.")
            return 0
        try:
            with open(self.cfg.cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            count = 0
            for ck in cookies:
                # Skip expired cookies if expiry is present
                try:
                    exp = ck.get("expiry")
                    if exp is not None and float(exp) < time.time():
                        logger.debug(f"Skip expired cookie {ck.get('name')}")
                        continue
                except Exception:
                    # If expiry cannot be parsed, attempt to use cookie anyway
                    pass
                # Selenium requires domain without leading dot sometimes
                if "domain" in ck and ck["domain"].startswith("."):
                    ck_copy = ck.copy()
                    ck_copy["domain"] = ck["domain"][1:]
                    try:
                        self.driver.add_cookie(ck_copy)  # type: ignore[arg-type]
                        count += 1
                        continue
                    except Exception:
                        pass  # Try original domain format below
                try:
                    self.driver.add_cookie(ck)  # type: ignore[arg-type]
                    count += 1
                except Exception as e:
                    logger.debug(f"Skip invalid cookie {ck.get('name')}: {e}")
            return count
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return 0

    def _save_cookies(self) -> None:
        if not self.cfg.cookies_path:
            return
        try:
            cookies = self.driver.get_cookies() if self.driver else []
            with open(self.cfg.cookies_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")

    def ensure_authenticated(self) -> bool:
        assert self.driver is not None
        
        # Navigate to target notebook directly
        if self.current_notebook_id:
            target_url = f"{NOTEBOOKLM_URL}notebook/{self.current_notebook_id}"
        else:
            target_url = NOTEBOOKLM_URL
            
        logger.info(f"Navigating to: {target_url}")
        self.driver.get(target_url)
        
        # Wait for page load
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            current_url = self.driver.current_url
            logger.debug(f"Current URL after navigation: {current_url}")
            
            # Check if we're authenticated (not on login page)
            if "signin" not in current_url and "accounts.google.com" not in current_url:
                logger.info("✅ Already authenticated via persistent session!")
                return True
            else:
                logger.warning("❌ Authentication required - need manual login")
                if not self.cfg.headless:
                    logger.info("Browser will stay open for manual authentication")
                    logger.info("Please login and navigate to your notebook")
                return False
                
        except TimeoutException:
            logger.error("Page load timed out")
            return False

    # --- NotebookLM actions (best-effort CSS selectors; may need adjustment) ---
    def navigate_to_notebook(self, notebook_id: str) -> str:
        assert self.driver is not None
        url = f"{NOTEBOOKLM_URL}notebook/{notebook_id}"
        self.driver.get(url)
        try:
            WebDriverWait(self.driver, self.cfg.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            raise RuntimeError("Notebook page did not load in time")
        return self.driver.current_url

    def send_chat_message(self, message: str) -> None:
        """Send chat message to NotebookLM"""
        assert self.driver is not None
        
        # Auto-navigate to notebook if needed
        if self.current_notebook_id:
            current_url = self.driver.current_url
            expected_url = f"notebook/{self.current_notebook_id}"
            if expected_url not in current_url:
                self.navigate_to_notebook(self.current_notebook_id)
        
        try:
            # Wait for NotebookLM interface to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Common NotebookLM chat input selectors (multiple fallbacks)
            chat_selectors = [
                "textarea[placeholder*='Ask']",  # Common "Ask about..." placeholder
                "textarea[data-testid*='chat']",  # Test ID patterns
                "textarea[aria-label*='message']",  # Accessibility labels
                "[contenteditable='true'][role='textbox']",  # Contenteditable inputs
                "input[type='text'][placeholder*='Ask']",  # Text inputs
                "textarea:not([disabled])",  # Any enabled textarea
            ]
            
            chat_input = None
            for selector in chat_selectors:
                try:
                    chat_input = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"Found chat input with selector: {selector}")
                    break
                except TimeoutException:
                    continue
            
            if chat_input is None:
                # Last resort: find any visible input/textarea
                try:
                    all_inputs = self.driver.find_elements(By.CSS_SELECTOR, "textarea, input[type='text']")
                    for inp in all_inputs:
                        if inp.is_displayed() and inp.is_enabled():
                            chat_input = inp
                            logger.info("Using fallback input element")
                            break
                except Exception:
                    pass
                    
            if chat_input is None:
                raise Exception("Could not find chat input element")
            
            # Clear and send message
            chat_input.clear()
            chat_input.send_keys(message)
            
            # Try to submit - multiple methods
            try:
                # Method 1: Press Enter
                from selenium.webdriver.common.keys import Keys
                chat_input.send_keys(Keys.RETURN)
                logger.info("Message sent via Enter key")
            except Exception:
                try:
                    # Method 2: Find submit button
                    submit_selectors = [
                        "button[type='submit']",
                        "button[aria-label*='Send']",
                        "button[data-testid*='send']",
                        "[role='button']:contains('Send')",
                    ]
                    for selector in submit_selectors:
                        try:
                            submit_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if submit_btn.is_displayed() and submit_btn.is_enabled():
                                submit_btn.click()
                                logger.info(f"Message sent via button: {selector}")
                                return
                        except Exception:
                            continue
                    
                    logger.warning("Could not find submit button, message may not be sent")
                except Exception as e:
                    logger.warning(f"Submit fallback failed: {e}")
            
        except TimeoutException:
            raise Exception("Chat interface not ready")
        except Exception as e:
            raise Exception(f"Failed to send message: {str(e)}")

    def get_chat_response(self, wait_for_completion: bool = True, max_wait: int = 60) -> str:
        """Get latest chat response from NotebookLM with streaming support"""
        assert self.driver is not None
        
        try:
            if wait_for_completion:
                logger.info("Waiting for streaming response to complete...")
                return self._wait_for_streaming_response(max_wait)
            else:
                # Quick response grab
                return self._get_current_response()
                
        except Exception as e:
            return f"Error retrieving response: {str(e)}"
    
    def _wait_for_streaming_response(self, max_wait: int = 60) -> str:
        """Wait for LLM streaming response to complete"""
        import time
        
        start_time = time.time()
        last_response = ""
        stable_count = 0
        required_stable_count = 3  # Need 3 consecutive identical reads
        
        # Streaming response indicators to watch for
        streaming_indicators = [
            # Common streaming/loading indicators
            "[class*='loading']",
            "[class*='typing']", 
            "[class*='generating']",
            "[aria-live='polite']",  # Screen reader live regions
            ".dots",  # Loading dots
            "[class*='spinner']",
            # Text patterns that indicate streaming
            "text()[contains(., '...')]",
            "text()[contains(., '▌')]",  # Cursor
        ]
        
        while time.time() - start_time < max_wait:
            current_response = self._get_current_response()
            
            # Check if still streaming (response is changing)
            if current_response == last_response:
                stable_count += 1
                logger.debug(f"Response stable ({stable_count}/{required_stable_count})")
                
                # Also check for streaming indicators
                is_streaming = self._check_streaming_indicators()
                if not is_streaming and stable_count >= required_stable_count:
                    logger.info("✅ Response appears complete")
                    return current_response
            else:
                stable_count = 0
                last_response = current_response
                logger.debug(f"Response updated: {current_response[:50]}...")
            
            time.sleep(1)  # Check every second
        
        logger.warning(f"Response wait timeout ({max_wait}s), returning current content")
        return last_response if last_response else "Response timeout - no content retrieved"
    
    def _check_streaming_indicators(self) -> bool:
        """Check if there are indicators that response is still streaming"""
        try:
            # Look for loading/typing indicators
            indicators = [
                "[class*='loading']",
                "[class*='typing']", 
                "[class*='generating']",
                "[class*='spinner']",
                ".dots"
            ]
            
            for indicator in indicators:
                elements = self.driver.find_elements(By.CSS_SELECTOR, indicator)
                for elem in elements:
                    if elem.is_displayed():
                        logger.debug(f"Found streaming indicator: {indicator}")
                        return True
                        
            return False
        except Exception:
            return False
    
    def _get_current_response(self) -> str:
        """Get current response text without waiting"""
        # Common response selectors for NotebookLM
        response_selectors = [
            # NotebookLM specific patterns
            "[data-testid*='response']",
            "[data-testid*='message']",
            "[role='article']",
            "[class*='message']:last-child",
            "[class*='response']:last-child",
            "[class*='chat-message']:last-child",
            # Generic chat patterns
            ".message:last-child",
            ".chat-bubble:last-child",
            "[class*='ai-response']",
            "[class*='assistant-message']",
        ]
        
        response_element = None
        best_response = ""
        
        # Try each selector
        for selector in response_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    # Get the last element (most recent)
                    elem = elements[-1]
                    text = elem.text.strip()
                    
                    # Choose the longest response (likely most complete)
                    if len(text) > len(best_response):
                        best_response = text
                        response_element = elem
                        logger.debug(f"Better response found with selector: {selector}")
                        
            except Exception:
                continue
        
        if not best_response:
            # Fallback: look for any substantial text content
            try:
                # Get all text-containing elements
                text_elements = self.driver.find_elements(By.CSS_SELECTOR, "p, div, span")
                for elem in reversed(text_elements[-20:]):  # Check last 20 elements
                    text = elem.text.strip()
                    # Look for AI-like responses (longer, substantive text)
                    if (len(text) > 50 and 
                        not any(skip in text.lower() for skip in [
                            "ask about", "loading", "error", "sign in", "menu"
                        ])):
                        best_response = text
                        logger.debug("Using fallback text element")
                        break
            except Exception:
                pass
        
        return best_response if best_response else "No response content found"

    def list_notebooks(self) -> List[Dict[str, Any]]:
        assert self.driver is not None
        self.driver.get(NOTEBOOKLM_URL)
        WebDriverWait(self.driver, self.cfg.timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        # Placeholder: return the current URL as one notebook entry
        return [{"id": "unknown", "title": "NotebookLM", "url": self.driver.current_url}]

    def upload_document(self, file_path: str, document_type: str) -> str:
        assert self.driver is not None
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        # Placeholder: in real UI, locate <input type="file"> and send file path
        return f"uploaded:{os.path.basename(file_path)}"

    def create_notebook(self, name: str, sources: List[str]) -> Dict[str, Any]:
        assert self.driver is not None
        # Placeholder: simulate created notebook
        created = {"id": "temp-id", "name": name, "sources": sources}
        self.current_notebook_id = created["id"]
        return created

    def get_notebook_insights(self, notebook_id: str) -> Dict[str, Any]:
        return {"id": notebook_id, "insights": ["Insight 1", "Insight 2"]}

    def search_in_notebook(self, query: str, notebook_id: str) -> List[str]:
        return [f"Match for {query} in {notebook_id}"]

    def export_conversation(self, format: str) -> str:
        return f"export://conversation.{format}"


# ----------------- MCP Server -----------------

def build_server(selenium_mgr: SeleniumManager) -> Server:
    server = Server("notebooklm-mcp")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(name="healthcheck", description="Check server health"),
            Tool(name="navigate_to_notebook", description="Navigate to a specific notebook"),
            Tool(name="send_chat_message", description="Send a message to NotebookLM chat"),
            Tool(name="get_chat_response", description="Get response from NotebookLM (waits for streaming completion)"),
            Tool(name="get_quick_response", description="Get current response without waiting for completion"),
            Tool(name="chat_with_notebook", description="Send message and get complete response (combined operation)"),
            Tool(name="upload_document", description="Upload a document to NotebookLM"),
            Tool(name="list_notebooks", description="List available notebooks"),
            Tool(name="create_notebook", description="Create a new notebook"),
            Tool(name="get_default_notebook", description="Get current default notebook ID"),
            Tool(name="set_default_notebook", description="Set default notebook ID"),
            Tool(name="get_notebook_insights", description="Get insights from a notebook"),
            Tool(name="search_in_notebook", description="Search within a notebook"),
            Tool(name="export_conversation", description="Export conversation history"),
            Tool(name="shutdown", description="Shutdown the server"),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "healthcheck":
                result = "ok"
            elif name == "navigate_to_notebook":
                notebook_id = arguments.get("notebook_id", "")
                selenium_mgr.current_notebook_id = notebook_id
                result = selenium_mgr.navigate_to_notebook(notebook_id)
            elif name == "get_default_notebook":
                result = selenium_mgr.current_notebook_id
            elif name == "set_default_notebook":
                notebook_id = arguments.get("notebook_id", "")
                selenium_mgr.current_notebook_id = notebook_id
                result = notebook_id
            elif name == "send_chat_message":
                message = arguments.get("message", "")
                selenium_mgr.send_chat_message(message)
                result = "sent"
            elif name == "get_chat_response":
                wait_for_completion = arguments.get("wait_for_completion", True)
                max_wait = arguments.get("max_wait", 60)
                result = selenium_mgr.get_chat_response(wait_for_completion, max_wait)
            elif name == "get_quick_response":
                result = selenium_mgr.get_chat_response(wait_for_completion=False)
            elif name == "chat_with_notebook":
                message = arguments.get("message", "")
                max_wait = arguments.get("max_wait", 60)
                # Send message
                selenium_mgr.send_chat_message(message)
                # Wait for complete response
                result = selenium_mgr.get_chat_response(wait_for_completion=True, max_wait=max_wait)
            elif name == "upload_document":
                file_path = arguments.get("file_path", "")
                document_type = arguments.get("document_type", "")
                result = selenium_mgr.upload_document(file_path, document_type)
            elif name == "list_notebooks":
                result = selenium_mgr.list_notebooks()
            elif name == "create_notebook":
                name_arg = arguments.get("name", "")
                sources = arguments.get("sources", [])
                result = selenium_mgr.create_notebook(name_arg, sources)
            elif name == "get_notebook_insights":
                notebook_id = arguments.get("notebook_id", "")
                result = selenium_mgr.get_notebook_insights(notebook_id)
            elif name == "search_in_notebook":
                query = arguments.get("query", "")
                notebook_id = arguments.get("notebook_id", "")
                result = selenium_mgr.search_in_notebook(query, notebook_id)
            elif name == "export_conversation":
                format_arg = arguments.get("format", "txt")
                result = selenium_mgr.export_conversation(format_arg)
            elif name == "shutdown":
                try:
                    selenium_mgr.stop()
                finally:
                    result = "shutting down"
            else:
                result = f"Unknown tool: {name}"
            
            return [TextContent(type="text", text=str(result))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    return server


async def amain(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NotebookLM MCP Server")
    parser.add_argument("--cookies", type=str, default=None, help="Path to cookies JSON file")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--timeout", type=int, default=30, help="WebDriver timeout seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--notebook", type=str, default=None, help="Default NotebookLM notebook id or full URL")
    args = parser.parse_args(argv)

    # Logging
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.debug else "INFO")

    # Normalize notebook id if full URL was provided
    nb_id = args.notebook
    if nb_id and nb_id.startswith("http"):
        # extract last path segment
        nb_id = nb_id.rstrip("/").split("/")[-1]

    cfg = ServerConfig(
        cookies_path=args.cookies,
        headless=args.headless,
        timeout=args.timeout,
        debug=args.debug,
        default_notebook_id=nb_id,
    )

    selenium_mgr = SeleniumManager(cfg)
    try:
        selenium_mgr.start()
        if not selenium_mgr.ensure_authenticated():
            logger.error("Authentication failed; exiting.")
            return 2

        server = build_server(selenium_mgr)
        logger.info("Starting MCP server over STDIO...")
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, {})
        return 0
    finally:
        selenium_mgr.stop()


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
