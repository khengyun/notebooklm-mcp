"""Deterministic tests for :mod:`notebooklm_mcp.auth_bridge`.

``export_storage_state`` drives a real Patchright/Playwright browser in
production. Here we monkeypatch ``patchright.async_api.async_playwright`` with a
faithful async fake (playwright -> chromium -> launch_persistent_context ->
context with pages/new_page/goto/storage_state/close, plus a top-level stop)
so the production control flow runs **without launching a browser**. The fake's
``storage_state(path=...)`` actually writes the target file, letting us assert
that the bytes land where the production code says they do.
"""

from __future__ import annotations

import asyncio
import json

import patchright.async_api as pw_module
import pytest

from notebooklm_mcp import auth_bridge
from notebooklm_mcp.config import AuthConfig, ServerConfig


# --------------------------------------------------------------------------- #
# default_storage_state_path
# --------------------------------------------------------------------------- #
def test_default_storage_state_path_uses_explicit(tmp_path):
    explicit = tmp_path / "custom" / "state.json"
    cfg = ServerConfig(auth=AuthConfig(storage_state_path=str(explicit)))
    # An explicit storage_state_path wins outright (expanded but otherwise
    # verbatim), independent of profile_dir.
    assert auth_bridge.default_storage_state_path(cfg) == explicit


def test_default_storage_state_path_defaults_under_profile(tmp_path):
    profile = tmp_path / "profile"
    cfg = ServerConfig(
        auth=AuthConfig(profile_dir=str(profile), storage_state_path=None)
    )
    # With no explicit path the default lives inside the profile dir.
    assert auth_bridge.default_storage_state_path(cfg) == (
        profile / "storage_state.json"
    )


def test_default_storage_state_path_expands_user(monkeypatch):
    cfg = ServerConfig(auth=AuthConfig(storage_state_path="~/state.json"))
    result = auth_bridge.default_storage_state_path(cfg)
    # The leading ~ must be expanded (no literal '~' component survives).
    assert "~" not in str(result)
    assert str(result).endswith("state.json")


# --------------------------------------------------------------------------- #
# export_storage_state — faithful async Playwright fake (no real browser).
# --------------------------------------------------------------------------- #
class FakePage:
    def __init__(self):
        self.goto_calls: list[tuple] = []

    async def goto(self, url, wait_until=None):
        self.goto_calls.append((url, wait_until))


class FakeContext:
    """Mirrors a BrowserContext: pages list, new_page, storage_state, close."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.new_page_calls = 0
        self.storage_state_calls: list[str] = []
        self.closed = False

    async def new_page(self):
        self.new_page_calls += 1
        page = FakePage()
        self.pages.append(page)
        return page

    async def storage_state(self, path):
        # Faithful: the real API persists the session to ``path``. We write a
        # marker file so the test can assert the bytes landed at this exact path.
        self.storage_state_calls.append(path)
        with open(path, "w") as fh:
            json.dump({"cookies": [], "origins": []}, fh)

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, context):
        self._context = context
        self.launch_kwargs = None

    async def launch_persistent_context(self, **kwargs):
        self.launch_kwargs = kwargs
        return self._context


class FakePlaywright:
    def __init__(self, context):
        self.chromium = FakeChromium(context)
        self.stopped = False

    async def stop(self):
        self.stopped = True


def make_async_playwright(playwright):
    """Drop-in for ``async_playwright``: ``().start()`` awaits to ``playwright``."""

    class _Factory:
        def start(self):
            return _AStart()

    class _AStart:
        def __await__(self):
            async def _coro():
                return playwright

            return _coro().__await__()

    return lambda: _Factory()


def install_fake_playwright(monkeypatch, *, pages):
    context = FakeContext(pages)
    playwright = FakePlaywright(context)
    # The production code does `from patchright.async_api import async_playwright`
    # at call time, so patch the symbol on the patchright module.
    monkeypatch.setattr(
        pw_module, "async_playwright", make_async_playwright(playwright)
    )
    return playwright, context


def test_export_storage_state_writes_target_and_returns_path(tmp_path, monkeypatch):
    out_path = tmp_path / "nested" / "dir" / "storage_state.json"
    profile = tmp_path / "profile"
    cfg = ServerConfig(headless=True, auth=AuthConfig(profile_dir=str(profile)))

    existing_page = FakePage()
    playwright, context = install_fake_playwright(monkeypatch, pages=[existing_page])

    result = asyncio.run(auth_bridge.export_storage_state(cfg, out_path))

    # Returns the path it was asked to write.
    assert result == out_path
    # The file was actually created at the target (fake storage_state wrote it).
    assert out_path.exists()
    assert json.loads(out_path.read_text()) == {"cookies": [], "origins": []}
    assert context.storage_state_calls == [str(out_path)]
    # Parent dir of the output was created (mkdir parents=True).
    assert out_path.parent.is_dir()
    # The persistent profile dir was created too.
    assert profile.is_dir()
    # It navigated to the app URL on the existing page (no new_page needed).
    assert existing_page.goto_calls == [(auth_bridge.APP_URL, "domcontentloaded")]
    assert context.new_page_calls == 0
    # Cleanup happened: context closed, playwright stopped.
    assert context.closed is True
    assert playwright.stopped is True


def test_export_storage_state_opens_new_page_when_none(tmp_path, monkeypatch):
    out_path = tmp_path / "storage_state.json"
    cfg = ServerConfig(auth=AuthConfig(profile_dir=str(tmp_path / "profile")))

    # No pre-existing pages -> the code must open one via new_page().
    playwright, context = install_fake_playwright(monkeypatch, pages=[])

    asyncio.run(auth_bridge.export_storage_state(cfg, out_path))

    assert context.new_page_calls == 1
    # The freshly created page is the one that navigated.
    assert context.pages and context.pages[-1].goto_calls == [
        (auth_bridge.APP_URL, "domcontentloaded")
    ]


def test_export_storage_state_passes_channel_and_binary(tmp_path, monkeypatch):
    out_path = tmp_path / "storage_state.json"
    cfg = ServerConfig(
        headless=True,
        chrome_binary="/opt/google/chrome/chrome",
        auth=AuthConfig(profile_dir=str(tmp_path / "profile"), chrome_channel="chrome"),
    )
    playwright, context = install_fake_playwright(monkeypatch, pages=[FakePage()])

    asyncio.run(auth_bridge.export_storage_state(cfg, out_path))

    kwargs = playwright.chromium.launch_kwargs
    # Channel + executable path are forwarded only when configured.
    assert kwargs["channel"] == "chrome"
    assert kwargs["executable_path"] == "/opt/google/chrome/chrome"
    assert kwargs["headless"] is True
    assert kwargs["user_data_dir"] == str((tmp_path / "profile").absolute())


def test_export_storage_state_omits_channel_when_unset(tmp_path, monkeypatch):
    out_path = tmp_path / "storage_state.json"
    cfg = ServerConfig(
        chrome_binary=None,
        auth=AuthConfig(profile_dir=str(tmp_path / "profile"), chrome_channel=None),
    )
    playwright, context = install_fake_playwright(monkeypatch, pages=[FakePage()])

    asyncio.run(auth_bridge.export_storage_state(cfg, out_path))

    kwargs = playwright.chromium.launch_kwargs
    # When channel/binary are unset they must NOT appear in the launch kwargs.
    assert "channel" not in kwargs
    assert "executable_path" not in kwargs


def test_export_storage_state_closes_on_error(tmp_path, monkeypatch):
    """If navigation explodes, the context must still be closed and playwright
    stopped (the finally blocks), and the error propagates."""
    out_path = tmp_path / "storage_state.json"
    cfg = ServerConfig(auth=AuthConfig(profile_dir=str(tmp_path / "profile")))

    class ExplodingPage(FakePage):
        async def goto(self, url, wait_until=None):
            raise RuntimeError("navigation failed")

    playwright, context = install_fake_playwright(monkeypatch, pages=[ExplodingPage()])

    with pytest.raises(RuntimeError, match="navigation failed"):
        asyncio.run(auth_bridge.export_storage_state(cfg, out_path))

    # Even on failure: context closed, playwright stopped, no file written.
    assert context.closed is True
    assert playwright.stopped is True
    assert not out_path.exists()
