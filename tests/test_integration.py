"""Real-browser integration tier (Patchright + Chrome).

These tests actually launch a browser, so they are the only ones that catch a
genuine launch/auth regression that the fully-mocked unit suites cannot. They
are gated by two markers (see ``tests/conftest.py``):

* ``browser``      — skipped when no ``DISPLAY`` (and not ``GITHUB_ACTIONS``);
* ``integration``  — skipped when ``SKIP_INTEGRATION_TESTS`` is set.

So a default local ``uv run pytest`` (no DISPLAY) skips them and stays fast and
green, while CI (which sets ``GITHUB_ACTIONS`` and installs Chrome) runs them.
When they DO run, they must fail loudly if the browser can't launch — that is
the entire point of this tier.

They are intentionally written without ``pytest-asyncio`` auto-mode: each test
drives the async client through ``asyncio.run`` so the gating/marking behaves
identically regardless of the project's asyncio config.
"""

import asyncio

import pytest

from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import AuthConfig, ServerConfig

# A generous ceiling: launching real Chrome + first navigation can be slow on
# a cold CI runner. If we blow past this, something is genuinely wrong.
LAUNCH_TIMEOUT_SECONDS = 120

pytestmark = [pytest.mark.browser, pytest.mark.integration]


def _fresh_config(tmp_path) -> ServerConfig:
    """A headless config pointed at an empty, throwaway profile dir.

    A fresh profile guarantees a signed-out session, which is exactly what we
    want to assert against deterministically.
    """
    profile_dir = tmp_path / "chrome_profile_integration"
    return ServerConfig(
        headless=True,
        default_notebook_id=None,
        auth=AuthConfig(
            profile_dir=str(profile_dir),
            use_persistent_session=True,
        ),
    )


def test_real_browser_smoke(tmp_path):
    """Launch a real browser, authenticate (expect signed-out), close twice.

    This is the one test that exercises the actual Patchright+Chrome launch
    path end to end. A fresh profile is not logged in, so ``authenticate()``
    must return ``False`` — but it must return a *bool*, not raise.
    """
    config = _fresh_config(tmp_path)

    async def scenario():
        client = NotebookLMClient(config)
        try:
            await asyncio.wait_for(client.start(), timeout=LAUNCH_TIMEOUT_SECONDS)
            # A live Playwright page must exist after start().
            assert client.page is not None
            assert client.driver is client.page

            authed = await asyncio.wait_for(
                client.authenticate(), timeout=LAUNCH_TIMEOUT_SECONDS
            )
            assert isinstance(authed, bool)
            # Fresh profile => not logged in.
            assert authed is False
            assert client.is_authenticated is False
        finally:
            # Always release the browser, and prove close() is idempotent.
            await client.close()
            assert client.page is None
            await client.close()  # second call must not raise
            assert client.page is None

    asyncio.run(scenario())


def test_real_authenticate_detects_signed_out(tmp_path):
    """A fresh profile must be detected as signed out via the real redirect.

    NotebookLM bounces a logged-out user to ``accounts.google.com``; the client
    keys off that to report ``authenticate() is False``. This asserts the real
    redirect path, complementing the mocked unit-level version.
    """
    config = _fresh_config(tmp_path)

    async def scenario():
        client = NotebookLMClient(config)
        try:
            await asyncio.wait_for(client.start(), timeout=LAUNCH_TIMEOUT_SECONDS)
            authed = await asyncio.wait_for(
                client.authenticate(), timeout=LAUNCH_TIMEOUT_SECONDS
            )
            assert authed is False
            assert client.is_authenticated is False
        finally:
            await client.close()

    asyncio.run(scenario())
