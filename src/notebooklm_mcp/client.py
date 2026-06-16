"""
Browser automation client for NotebookLM interactions.

Engine: Patchright (undetected Playwright). Chosen over Selenium +
undetected-chromedriver because it:

* eliminates the chromedriver/Chrome version-matching failure
  (``SessionNotCreatedException``) — Patchright manages its own driver and
  drives the installed Chrome via ``channel="chrome"``;
* patches the ``Runtime.enable`` CDP leak that Google's bot detection keys on;
* is async-native, so the whole client is real ``async`` instead of Selenium
  shoved through ``run_in_executor``.

All DOM selectors live in :mod:`notebooklm_mcp.selectors` so UI drift is a
one-file change.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from loguru import logger
from patchright.async_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)
from patchright.async_api import (
    Error as PlaywrightError,
)
from patchright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from . import selectors as S
from .config import ServerConfig
from .exceptions import AuthenticationError, ChatError, NavigationError


class NotebookLMClient:
    """High-level async client for NotebookLM automation."""

    #: The browser/DOM engine drives chat only; it cannot do UI-independent
    #: notebook/source management (that requires the RPC engine).
    supports_management = False

    def __init__(self, config: ServerConfig):
        self.config = config
        self._playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.current_notebook_id: Optional[str] = config.default_notebook_id
        self._is_authenticated = False

    # Backwards-compatible alias: monitoring.py historically read
    # ``client.driver``. The Playwright ``Page`` exposes ``.url`` like the old
    # Selenium driver, so existing health checks keep working.
    @property
    def driver(self) -> Optional[Page]:
        return self.page

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """Launch a persistent, undetected Chrome session.

        Idempotent: calling twice is a no-op while a page is live.
        """
        if self.page is not None:
            return

        profile_path = Path(self.config.auth.profile_dir).expanduser()
        if self.config.auth.use_persistent_session:
            profile_path = profile_path.absolute()
            profile_path.mkdir(parents=True, exist_ok=True)

        launch_args = [
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

        launch_kwargs: dict = {
            "user_data_dir": (
                str(profile_path) if self.config.auth.use_persistent_session else ""
            ),
            "headless": self.config.headless,
            "args": launch_args,
            "no_viewport": True,
        }
        # ``channel="chrome"`` uses the real installed Chrome (best stealth and
        # the configuration proven against NotebookLM). Fall back to Patchright's
        # bundled Chromium if Chrome isn't present.
        if self.config.auth.chrome_channel:
            launch_kwargs["channel"] = self.config.auth.chrome_channel
        if self.config.chrome_binary:
            launch_kwargs["executable_path"] = self.config.chrome_binary

        try:
            self._playwright = await async_playwright().start()
            self.context = await self._launch_context(launch_kwargs)
        except PlaywrightError as exc:
            # Most common cause: ``channel="chrome"`` requested but no system
            # Chrome. Retry once with the bundled Chromium.
            if launch_kwargs.pop("channel", None) is not None:
                logger.warning(
                    f"Chrome channel launch failed ({exc}); "
                    "retrying with bundled Chromium"
                )
                self.context = await self._launch_context(launch_kwargs)
            else:
                await self._safe_shutdown()
                raise AuthenticationError(f"Failed to launch browser: {exc}") from exc

        self.page = (
            self.context.pages[0]
            if self.context.pages
            else await self.context.new_page()
        )
        self.page.set_default_timeout(self.config.timeout * 1000)
        logger.info("Patchright browser session started")

    async def _launch_context(self, launch_kwargs: dict) -> BrowserContext:
        assert self._playwright is not None
        return await self._playwright.chromium.launch_persistent_context(
            **launch_kwargs
        )

    async def close(self) -> None:
        """Close the browser session. Idempotent."""
        await self._safe_shutdown()
        self._is_authenticated = False

    async def _safe_shutdown(self) -> None:
        for closer in (self._close_context, self._stop_playwright):
            try:
                await closer()
            except Exception as exc:  # pragma: no cover - best-effort cleanup
                logger.debug(f"Shutdown step failed: {exc}")
        self.context = None
        self.page = None
        self._playwright = None

    async def _close_context(self) -> None:
        if self.context is not None:
            await self.context.close()

    async def _stop_playwright(self) -> None:
        if self._playwright is not None:
            await self._playwright.stop()

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #
    async def authenticate(self) -> bool:
        """Navigate to the target notebook and detect login state.

        Auth is detected positively: we must be on the NotebookLM host, not
        bounced to a Google sign-in URL. When a notebook is loaded we also
        confirm the chat composer is present.
        """
        if self.page is None:
            raise AuthenticationError("Browser not started")

        target_url = self.config.base_url
        if self.current_notebook_id:
            target_url = f"{self.config.base_url}/notebook/{self.current_notebook_id}"

        logger.info(f"Navigating to: {target_url}")
        try:
            await self.page.goto(target_url, wait_until="domcontentloaded")
        except PlaywrightTimeoutError as exc:
            raise AuthenticationError("Page load timed out") from exc

        current_url = self.page.url
        logger.debug(f"Current URL after navigation: {current_url}")

        if self._url_is_signed_out(current_url):
            logger.warning("Authentication required - manual Google login needed")
            self._is_authenticated = False
            return False

        if S.APP_HOST not in current_url:
            # Landed somewhere unexpected (interstitial/consent): treat as
            # not-authenticated rather than risk a false positive.
            logger.warning(f"Unexpected post-login URL: {current_url}")
            self._is_authenticated = False
            return False

        # On the app host and not at a sign-in page → authenticated. If a
        # notebook is loaded, confirm the composer renders (best-effort).
        if self.current_notebook_id:
            composer = await self._find_first(S.CHAT_INPUT, timeout=8000)
            if composer is None:
                logger.warning("On app host but chat composer not found yet")
        logger.info("Authenticated via persistent session")
        self._is_authenticated = True
        return True

    @staticmethod
    def _url_is_signed_out(url: str) -> bool:
        return any(marker in url for marker in S.SIGNED_OUT_URL_MARKERS)

    # ------------------------------------------------------------------ #
    # Messaging
    # ------------------------------------------------------------------ #
    async def send_message(self, message: str) -> None:
        """Type a message into the chat composer and submit it."""
        if self.page is None or not self._is_authenticated:
            raise ChatError("Not authenticated or browser not ready")

        await self._ensure_on_notebook()

        composer = await self._find_first(S.CHAT_INPUT, timeout=self._timeout_ms)
        if composer is None:
            raise ChatError("Could not find chat input element")

        try:
            await composer.click()
            await composer.fill(message)
            await composer.press("Enter")
            logger.info("Message sent")
        except PlaywrightError as exc:
            raise ChatError(f"Failed to submit message: {exc}") from exc

    async def _ensure_on_notebook(self) -> None:
        if not self.current_notebook_id or self.page is None:
            return
        if f"notebook/{self.current_notebook_id}" not in self.page.url:
            await self._navigate(self.current_notebook_id)

    # ------------------------------------------------------------------ #
    # Responses
    # ------------------------------------------------------------------ #
    async def get_response(
        self, wait_for_completion: bool = True, max_wait: Optional[int] = None
    ) -> str:
        """Return the latest assistant response.

        When ``wait_for_completion`` is set, wait for the streaming/thinking
        indicator to clear and the text to stabilize before reading.
        """
        if self.page is None:
            raise ChatError("Browser not ready")

        budget = max_wait or self.config.streaming_timeout
        if wait_for_completion:
            await self._wait_until_idle(budget)
        text = await self._read_latest_response()
        return text or "No response content found"

    async def _wait_until_idle(self, max_wait: int) -> None:
        """Block until the response stops changing (stability poll)."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max_wait
        required_stable = self.config.response_stability_checks
        last = ""
        stable = 0

        logger.info("Waiting for response to complete...")
        while loop.time() < deadline:
            current = await self._read_latest_response()
            thinking = await self._is_thinking()

            if current == last and current:
                stable += 1
                if not thinking and stable >= required_stable:
                    logger.info("Response complete")
                    return
            else:
                stable = 0
                last = current
            await asyncio.sleep(1)

        logger.warning(f"Response wait timed out ({max_wait}s)")

    async def _is_thinking(self) -> bool:
        if self.page is None:
            return False
        for selector in S.THINKING:
            try:
                if await self.page.locator(selector).first.is_visible():
                    return True
            except PlaywrightError:
                continue
        return False

    async def _read_latest_response(self) -> str:
        """Read the text of the newest assistant message."""
        if self.page is None:
            return ""
        for selector in S.RESPONSE:
            try:
                locator = self.page.locator(selector)
                count = await locator.count()
                if count:
                    text = await locator.nth(count - 1).inner_text()
                    if text and text.strip():
                        return text.strip()
            except PlaywrightError:
                continue
        return ""

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #
    async def navigate_to_notebook(self, notebook_id: str) -> str:
        if self.page is None:
            raise NavigationError("Browser not started")
        return await self._navigate(notebook_id)

    async def _navigate(self, notebook_id: str) -> str:
        assert self.page is not None
        url = f"{self.config.base_url}/notebook/{notebook_id}"
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightTimeoutError as exc:
            raise NavigationError(
                f"Failed to navigate to notebook {notebook_id}"
            ) from exc
        self.current_notebook_id = notebook_id
        return self.page.url

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @property
    def _timeout_ms(self) -> int:
        return self.config.timeout * 1000

    async def _find_first(
        self, candidates: list[str], timeout: int
    ) -> Optional[Locator]:
        """Return the first selector's locator that becomes visible, else None.

        The timeout is split across candidates so the total wait is bounded.
        """
        if self.page is None:
            return None
        per_selector = max(500, timeout // max(1, len(candidates)))
        for selector in candidates:
            try:
                locator = self.page.locator(selector).first
                await locator.wait_for(state="visible", timeout=per_selector)
                logger.debug(f"Matched selector: {selector}")
                return locator
            except PlaywrightTimeoutError:
                continue
            except PlaywrightError:
                continue
        return None
