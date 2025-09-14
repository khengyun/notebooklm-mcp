"""
Browser automation client for NotebookLM interactions
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    import undetected_chromedriver as uc

    USE_UNDETECTED = True
except ImportError:
    USE_UNDETECTED = False

from .config import ServerConfig
from .exceptions import AuthenticationError, ChatError, NavigationError


class NotebookLMClient:
    """High-level client for NotebookLM automation"""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.driver: Optional[webdriver.Chrome] = None
        self.current_notebook_id: Optional[str] = config.default_notebook_id
        self._is_authenticated = False

    async def start(self) -> None:
        """Start browser session"""
        await asyncio.get_event_loop().run_in_executor(None, self._start_browser)

    def _start_browser(self) -> None:
        """Initialize browser with proper configuration"""
        if USE_UNDETECTED:
            logger.info("Using undetected-chromedriver for better compatibility")

            # Create persistent profile directory
            if self.config.auth.use_persistent_session:
                profile_path = Path(self.config.auth.profile_dir).absolute()
                profile_path.mkdir(exist_ok=True)

            options = uc.ChromeOptions()
            if self.config.auth.use_persistent_session:
                options.add_argument(f"--user-data-dir={profile_path}")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-extensions")

            if self.config.headless:
                options.add_argument("--headless=new")

            self.driver = uc.Chrome(options=options, version_main=None)
        else:
            logger.warning(
                "undetected-chromedriver not available, using regular Selenium"
            )
        # Fallback implementation with regular ChromeDriver
        self._start_regular_chrome()

        if self.driver is None:
            raise RuntimeError("Failed to initialize browser driver")
        self.driver.set_page_load_timeout(self.config.timeout)

    def _start_regular_chrome(self) -> None:
        """Fallback Chrome initialization"""
        opts = ChromeOptions()

        # Anti-detection options
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        # User agent
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        if self.config.headless:
            opts.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=opts)

        # Remove automation indicators
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    async def authenticate(self) -> bool:
        """Authenticate with NotebookLM"""
        if not self.driver:
            raise AuthenticationError("Browser not started")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._authenticate_sync
        )

    def _authenticate_sync(self) -> bool:
        """Synchronous authentication logic"""
        if self.driver is None:
            raise RuntimeError("Browser driver not initialized")
            
        target_url = self.config.base_url
        if self.current_notebook_id:
            target_url = f"{self.config.base_url}/notebook/{self.current_notebook_id}"

        logger.info(f"Navigating to: {target_url}")
        self.driver.get(target_url)

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            current_url = self.driver.current_url
            logger.debug(f"Current URL after navigation: {current_url}")

            # Check if authenticated
            if "signin" not in current_url and "accounts.google.com" not in current_url:
                logger.info("✅ Already authenticated via persistent session!")
                self._is_authenticated = True
                return True
            else:
                logger.warning("❌ Authentication required - need manual login")
                if not self.config.headless:
                    logger.info("Browser will stay open for manual authentication")
                self._is_authenticated = False
                return False

        except TimeoutException:
            raise AuthenticationError("Page load timed out during authentication")

    async def send_message(self, message: str) -> None:
        """Send chat message to NotebookLM"""
        if not self.driver or not self._is_authenticated:
            raise ChatError("Not authenticated or browser not ready")

        await asyncio.get_event_loop().run_in_executor(
            None, self._send_message_sync, message
        )

    def _send_message_sync(self, message: str) -> None:
        """Synchronous message sending"""
        if self.driver is None:
            raise RuntimeError("Browser driver not initialized")
            
        # Ensure we're on the right notebook
        if self.current_notebook_id:
            current_url = self.driver.current_url
            expected_url = f"notebook/{self.current_notebook_id}"
            if expected_url not in current_url:
                self._navigate_to_notebook_sync(self.current_notebook_id)

        # Find chat input with multiple fallback selectors
        chat_selectors = [
            "textarea[placeholder*='Ask']",
            "textarea[data-testid*='chat']",
            "textarea[aria-label*='message']",
            "[contenteditable='true'][role='textbox']",
            "input[type='text'][placeholder*='Ask']",
            "textarea:not([disabled])",
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
            raise ChatError("Could not find chat input element")

        # Send message
        chat_input.clear()
        chat_input.send_keys(message)

        # Submit message
        try:
            from selenium.webdriver.common.keys import Keys

            chat_input.send_keys(Keys.RETURN)
            logger.info("Message sent successfully")
        except Exception as e:
            raise ChatError(f"Failed to submit message: {e}")

    async def get_response(
        self, wait_for_completion: bool = True, max_wait: int = 60
    ) -> str:
        """Get response from NotebookLM with streaming support"""
        if not self.driver:
            raise ChatError("Browser not ready")

        if wait_for_completion:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._wait_for_streaming_response, max_wait
            )
        else:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._get_current_response
            )

    def _wait_for_streaming_response(self, max_wait: int) -> str:
        """Wait for streaming response to complete"""
        start_time = time.time()
        last_response = ""
        stable_count = 0
        required_stable_count = self.config.response_stability_checks

        logger.info("Waiting for streaming response to complete...")

        while time.time() - start_time < max_wait:
            current_response = self._get_current_response()

            if current_response == last_response:
                stable_count += 1
                logger.debug(
                    f"Response stable ({stable_count}/{required_stable_count})"
                )

                # Check for streaming indicators
                is_streaming = self._check_streaming_indicators()
                if not is_streaming and stable_count >= required_stable_count:
                    logger.info("✅ Response appears complete")
                    return current_response
            else:
                stable_count = 0
                last_response = current_response
                logger.debug(f"Response updated: {current_response[:50]}...")

            time.sleep(1)

        logger.warning(
            f"Response wait timeout ({max_wait}s), returning current content"
        )
        return (
            last_response
            if last_response
            else "Response timeout - no content retrieved"
        )

    def _check_streaming_indicators(self) -> bool:
        """Check if response is still streaming"""
        if self.driver is None:
            return False
            
        try:
            indicators = [
                "[class*='loading']",
                "[class*='typing']",
                "[class*='generating']",
                "[class*='spinner']",
                ".dots",
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
        """Get current response text"""
        if self.driver is None:
            return ""
            
        response_selectors = [
            "[data-testid*='response']",
            "[data-testid*='message']",
            "[role='article']",
            "[class*='message']:last-child",
            "[class*='response']:last-child",
            "[class*='chat-message']:last-child",
            ".message:last-child",
            ".chat-bubble:last-child",
            "[class*='ai-response']",
            "[class*='assistant-message']",
        ]

        best_response = ""

        for selector in response_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    elem = elements[-1]
                    text = elem.text.strip()

                    if len(text) > len(best_response):
                        best_response = text

            except Exception:
                continue

        if not best_response:
            # Fallback to any substantial text
            try:
                text_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "p, div, span"
                )
                for elem in reversed(text_elements[-20:]):
                    text = elem.text.strip()
                    if len(text) > 50 and not any(
                        skip in text.lower()
                        for skip in ["ask about", "loading", "error", "sign in", "menu"]
                    ):
                        best_response = text
                        break
            except Exception:
                pass

        return best_response if best_response else "No response content found"

    async def navigate_to_notebook(self, notebook_id: str) -> str:
        """Navigate to specific notebook"""
        if not self.driver:
            raise NavigationError("Browser not started")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._navigate_to_notebook_sync, notebook_id
        )

    def _navigate_to_notebook_sync(self, notebook_id: str) -> str:
        """Synchronous notebook navigation"""
        if self.driver is None:
            raise RuntimeError("Browser driver not initialized")
            
        url = f"{self.config.base_url}/notebook/{notebook_id}"
        self.driver.get(url)

        try:
            WebDriverWait(self.driver, self.config.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            self.current_notebook_id = notebook_id
            return self.driver.current_url
        except TimeoutException:
            raise NavigationError(f"Failed to navigate to notebook {notebook_id}")

    async def close(self) -> None:
        """Close browser session"""
        if self.driver:
            await asyncio.get_event_loop().run_in_executor(None, self.driver.quit)
            self.driver = None
            self._is_authenticated = False
