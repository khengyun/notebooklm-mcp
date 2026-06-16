"""
Deterministic unit tests for the async Patchright-based ``NotebookLMClient``.

No real browser, no network, no real sleeps. The Playwright tree is replaced by
the *faithful* async fakes in ``conftest.py`` (``FakePage`` / ``FakeLocator`` /
``FakeElement``). Crucially, these tests DRIVE THE REAL HELPERS
(``_find_first``, ``_read_latest_response``, ``_is_thinking``,
``_wait_until_idle``) through the fakes instead of monkeypatching them away, so
the actual DOM-walking / selector-fallback / stability-poll logic is exercised.
``asyncio.sleep`` is the only thing patched out (to avoid real waits).
"""

import patchright.async_api as pw
import pytest

from notebooklm_mcp import selectors as S
from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import AuthenticationError, ChatError, NavigationError

from conftest import (
    FakeContext,
    FakeElement,
    FakeLocator,
    FakePage,
    FakePlaywright,
    make_async_playwright,
)

# Real Playwright error classes (TimeoutError subclasses Error) for the branches
# that catch/raise them.
PWError = pw.Error
PWTimeout = pw.TimeoutError


@pytest.fixture
def no_sleep(monkeypatch):
    """Patch only ``asyncio.sleep`` so stability polls run with zero real wait."""

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("notebooklm_mcp.client.asyncio.sleep", _no_sleep)
    return _no_sleep


# --------------------------------------------------------------------------- #
# start()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_start_is_noop_when_page_already_set(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    existing = FakePage()
    client.page = existing

    # If start() tried to launch anything, this would explode.
    def boom():
        raise AssertionError("async_playwright must not be touched")

    monkeypatch.setattr("notebooklm_mcp.client.async_playwright", boom)

    await client.start()

    assert client.page is existing


@pytest.mark.asyncio
async def test_start_happy_path(monkeypatch, tmp_path):
    config = ServerConfig(timeout=30)
    config.auth.profile_dir = str(tmp_path / "profile")
    config.auth.use_persistent_session = True
    client = NotebookLMClient(config)

    page = FakePage()
    context = FakeContext(pages=[page])
    playwright = FakePlaywright()

    monkeypatch.setattr(
        "notebooklm_mcp.client.async_playwright",
        make_async_playwright(playwright),
    )

    captured = {}

    async def fake_launch(self, launch_kwargs):
        captured["kwargs"] = launch_kwargs
        return context

    monkeypatch.setattr(NotebookLMClient, "_launch_context", fake_launch)

    await client.start()

    assert client.page is page
    assert client._playwright is playwright
    assert client.context is context
    assert page.default_timeout == config.timeout * 1000
    # Persistent session => the profile dir was created.
    assert (tmp_path / "profile").is_dir()
    # Channel was passed through from auth config (default "chrome").
    assert captured["kwargs"]["channel"] == "chrome"


@pytest.mark.asyncio
async def test_start_non_persistent_session_skips_profile_dir(monkeypatch, tmp_path):
    """With ``use_persistent_session=False`` the profile dir is NOT created and
    ``user_data_dir`` is empty (covers the client.py:78->82 branch skip).
    """
    config = ServerConfig()
    profile = tmp_path / "should-not-exist"
    config.auth.profile_dir = str(profile)
    config.auth.use_persistent_session = False
    client = NotebookLMClient(config)

    context = FakeContext(pages=[FakePage()])
    playwright = FakePlaywright()
    monkeypatch.setattr(
        "notebooklm_mcp.client.async_playwright",
        make_async_playwright(playwright),
    )

    captured = {}

    async def fake_launch(self, launch_kwargs):
        captured["kwargs"] = launch_kwargs
        return context

    monkeypatch.setattr(NotebookLMClient, "_launch_context", fake_launch)

    await client.start()

    assert not profile.exists()
    assert captured["kwargs"]["user_data_dir"] == ""


@pytest.mark.asyncio
async def test_start_passes_chrome_binary_as_executable_path(monkeypatch, tmp_path):
    """When ``chrome_binary`` is set it is forwarded as ``executable_path``
    (covers client.py:103-104).
    """
    config = ServerConfig(timeout=15, chrome_binary="/opt/chrome/chrome")
    config.auth.profile_dir = str(tmp_path / "profile")
    config.auth.use_persistent_session = True
    client = NotebookLMClient(config)

    context = FakeContext(pages=[FakePage()])
    playwright = FakePlaywright()
    monkeypatch.setattr(
        "notebooklm_mcp.client.async_playwright",
        make_async_playwright(playwright),
    )

    captured = {}

    async def fake_launch(self, launch_kwargs):
        captured["kwargs"] = launch_kwargs
        return context

    monkeypatch.setattr(NotebookLMClient, "_launch_context", fake_launch)

    await client.start()

    assert captured["kwargs"]["executable_path"] == "/opt/chrome/chrome"


@pytest.mark.asyncio
async def test_start_creates_page_when_context_empty(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    context = FakeContext(pages=[])  # no pages -> new_page() path
    playwright = FakePlaywright()

    monkeypatch.setattr(
        "notebooklm_mcp.client.async_playwright",
        make_async_playwright(playwright),
    )

    async def fake_launch(self, launch_kwargs):
        return context

    monkeypatch.setattr(NotebookLMClient, "_launch_context", fake_launch)

    await client.start()

    assert client.page is context.new_pages[0]


@pytest.mark.asyncio
async def test_start_channel_fallback(monkeypatch):
    """First launch (with channel) raises; retry without channel succeeds."""
    config = ServerConfig()
    config.auth.chrome_channel = "chrome"
    client = NotebookLMClient(config)

    page = FakePage()
    context = FakeContext(pages=[page])
    playwright = FakePlaywright()

    monkeypatch.setattr(
        "notebooklm_mcp.client.async_playwright",
        make_async_playwright(playwright),
    )

    attempts = []

    async def fake_launch(self, launch_kwargs):
        attempts.append(dict(launch_kwargs))
        if "channel" in launch_kwargs:
            raise PWError("no system chrome")
        return context

    monkeypatch.setattr(NotebookLMClient, "_launch_context", fake_launch)

    await client.start()

    assert len(attempts) == 2
    assert attempts[0]["channel"] == "chrome"
    assert "channel" not in attempts[1]
    assert client.page is page


@pytest.mark.asyncio
async def test_start_raises_auth_error_when_no_channel_to_drop(monkeypatch):
    """Launch fails and there is no channel to retry without -> AuthenticationError.

    Exercises the real error/fallback branch (client.py:104): no ``channel``
    present means there is nothing to pop, so ``_safe_shutdown`` runs and an
    ``AuthenticationError`` is raised.
    """
    config = ServerConfig()
    config.auth.chrome_channel = None  # nothing to pop
    client = NotebookLMClient(config)
    playwright = FakePlaywright()

    monkeypatch.setattr(
        "notebooklm_mcp.client.async_playwright",
        make_async_playwright(playwright),
    )

    async def fake_launch(self, launch_kwargs):
        raise PWError("kaboom")

    shutdown_called = {}

    async def fake_shutdown(self):
        shutdown_called["yes"] = True

    monkeypatch.setattr(NotebookLMClient, "_launch_context", fake_launch)
    monkeypatch.setattr(NotebookLMClient, "_safe_shutdown", fake_shutdown)

    with pytest.raises(AuthenticationError, match="Failed to launch browser"):
        await client.start()

    assert shutdown_called.get("yes") is True


@pytest.mark.asyncio
async def test_launch_context_invokes_chromium_persistent_context(monkeypatch):
    """The real ``_launch_context`` (client.py:131-132) forwards kwargs to
    ``chromium.launch_persistent_context`` and returns its result.
    """
    config = ServerConfig()
    client = NotebookLMClient(config)

    context = FakeContext(pages=[FakePage()])
    received = {}

    class FakeChromium:
        async def launch_persistent_context(self, **kwargs):
            received.update(kwargs)
            return context

    class FakePlaywrightWithChromium(FakePlaywright):
        def __init__(self):
            super().__init__()
            self.chromium = FakeChromium()

    client._playwright = FakePlaywrightWithChromium()

    launch_kwargs = {"user_data_dir": "/tmp/profile", "headless": True}
    result = await client._launch_context(launch_kwargs)

    assert result is context
    assert received == launch_kwargs


@pytest.mark.asyncio
async def test_start_drives_real_launch_context_and_fallback(monkeypatch, tmp_path):
    """End-to-end through the REAL ``_launch_context``: first call (with the
    ``channel`` kwarg) raises a Playwright ``Error``; ``start`` retries via the
    real ``_launch_context`` again, which succeeds with the bundled Chromium.
    """
    config = ServerConfig(timeout=10)
    config.auth.chrome_channel = "chrome"
    config.auth.profile_dir = str(tmp_path / "profile")
    config.auth.use_persistent_session = True
    client = NotebookLMClient(config)

    page = FakePage()
    context = FakeContext(pages=[page])
    calls = []

    class FakeChromium:
        async def launch_persistent_context(self, **kwargs):
            calls.append(dict(kwargs))
            if "channel" in kwargs:
                raise PWError("no system chrome installed")
            return context

    class FakePlaywrightWithChromium(FakePlaywright):
        def __init__(self):
            super().__init__()
            self.chromium = FakeChromium()

    monkeypatch.setattr(
        "notebooklm_mcp.client.async_playwright",
        make_async_playwright(FakePlaywrightWithChromium()),
    )

    await client.start()

    assert client.page is page
    assert len(calls) == 2
    assert calls[0]["channel"] == "chrome"
    assert "channel" not in calls[1]


# --------------------------------------------------------------------------- #
# authenticate()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_authenticate_requires_started_browser():
    client = NotebookLMClient(ServerConfig())
    with pytest.raises(AuthenticationError):
        await client.authenticate()


@pytest.mark.asyncio
async def test_authenticate_signed_out_returns_false(client_factory):
    page = FakePage(goto_url="https://accounts.google.com/signin")
    client = client_factory(page=page, notebook_id="abc")

    result = await client.authenticate()

    assert result is False
    assert client.is_authenticated is False


@pytest.mark.asyncio
async def test_authenticate_signin_path_marker_returns_false(client_factory):
    """A ``/signin`` marker on the app host itself still reads as signed out
    (kills an inversion of the signed-out check that would auth on this URL).
    """
    page = FakePage(goto_url="https://notebooklm.google.com/signin?foo=1")
    client = client_factory(page=page, notebook_id="abc")

    result = await client.authenticate()

    assert result is False
    assert client.is_authenticated is False


@pytest.mark.asyncio
async def test_authenticate_non_app_host_returns_false(client_factory):
    page = FakePage(goto_url="https://example.com/whatever")
    client = client_factory(page=page, notebook_id="abc")

    result = await client.authenticate()

    assert result is False
    assert client.is_authenticated is False


@pytest.mark.asyncio
async def test_authenticate_app_host_with_notebook_returns_true(client_factory):
    """REAL ``_find_first`` runs against a page that exposes the composer via
    the first CHAT_INPUT selector; auth succeeds and the composer is confirmed.
    """
    composer = FakeElement(visible=True)
    page = FakePage(
        url="https://notebooklm.google.com/notebook/abc",
        goto_url="https://notebooklm.google.com/notebook/abc",
        selectors={S.CHAT_INPUT[0]: [composer]},
    )
    client = client_factory(page=page, notebook_id="abc")

    result = await client.authenticate()

    assert result is True
    assert client.is_authenticated is True
    assert page.goto_calls == ["https://notebooklm.google.com/notebook/abc"]
    # The real _find_first actually probed the composer selector.
    assert S.CHAT_INPUT[0] in page.locator_calls


@pytest.mark.asyncio
async def test_authenticate_no_notebook_skips_composer_probe(client_factory):
    """No notebook loaded -> the composer best-effort path is skipped, but auth
    on the app host still succeeds (covers the 199->203 branch skip).
    """
    page = FakePage(
        url="https://notebooklm.google.com",
        goto_url="https://notebooklm.google.com",
    )
    client = client_factory(page=page, notebook_id=None)
    client.current_notebook_id = None

    result = await client.authenticate()

    assert result is True
    assert client.is_authenticated is True
    # No composer probe happened.
    assert page.locator_calls == []


@pytest.mark.asyncio
async def test_authenticate_tolerates_missing_composer(no_sleep, client_factory):
    """Composer never becomes visible -> REAL ``_find_first`` returns None after
    exhausting CHAT_INPUT; that is only a warning, so auth still succeeds.
    """
    page = FakePage(
        url="https://notebooklm.google.com/notebook/abc",
        goto_url="https://notebooklm.google.com/notebook/abc",
        # No CHAT_INPUT selectors registered -> every wait_for times out.
    )
    client = client_factory(page=page, notebook_id="abc")

    assert await client.authenticate() is True
    assert client.is_authenticated is True
    # The real _find_first probed every CHAT_INPUT candidate before giving up.
    for selector in S.CHAT_INPUT:
        assert selector in page.locator_calls


@pytest.mark.asyncio
async def test_authenticate_goto_timeout_raises(client_factory):
    page = FakePage(goto_error=PWTimeout("page load timed out"))
    client = client_factory(page=page, notebook_id="abc")

    with pytest.raises(AuthenticationError):
        await client.authenticate()


# --------------------------------------------------------------------------- #
# send_message()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_send_message_requires_page():
    client = NotebookLMClient(ServerConfig())
    client._is_authenticated = True
    with pytest.raises(ChatError):
        await client.send_message("hi")


@pytest.mark.asyncio
async def test_send_message_requires_authentication(client_factory):
    client = client_factory(page=FakePage(), authenticated=False)
    with pytest.raises(ChatError):
        await client.send_message("hi")


@pytest.mark.asyncio
async def test_send_message_no_composer_raises(no_sleep, client_factory):
    """No composer anywhere -> REAL ``_find_first`` returns None -> ChatError."""
    # Already on the notebook so _ensure_on_notebook is a no-op (no goto needed).
    page = FakePage(url="https://notebooklm.google.com/notebook/abc")
    client = client_factory(page=page, notebook_id="abc", authenticated=True)

    with pytest.raises(ChatError, match="Could not find chat input"):
        await client.send_message("hi")


@pytest.mark.asyncio
async def test_send_message_happy_path_drives_real_find_first(client_factory):
    """The REAL ``_find_first`` must pick the chat composer
    (``textarea.query-box-input``) and the composer -- not anything else --
    receives click -> fill -> press in order.
    """
    # Pre-built locator (via ``locators=``) so call ordering is recorded on the
    # exact object the client interacts with.
    composer = FakeLocator(elements=[FakeElement(visible=True)])
    page = FakePage(
        url="https://notebooklm.google.com/notebook/abc",
        locators={S.CHAT_INPUT[0]: composer},
    )
    client = client_factory(page=page, notebook_id="abc", authenticated=True)

    await client.send_message("hello world")

    # _find_first wait_for's the composer first, then click/fill/press in order.
    assert composer.calls == [
        "wait_for",
        "click",
        ("fill", "hello world"),
        ("press", "Enter"),
    ]
    # And the very first selector probed was the verified composer selector.
    assert page.locator_calls[0] == S.CHAT_INPUT[0]


@pytest.mark.asyncio
async def test_send_message_picks_composer_not_decoy(client_factory):
    """Page has a DECOY textarea (a non-CHAT_INPUT selector) AND the real
    ``query-box-input``. ``_find_first`` must select the composer via the
    selector list -- never the decoy. Proven by checking the composer received
    the keystrokes and the decoy did not.
    """
    # A visible decoy that would win under any blind catch-all, but its selector
    # is NOT in S.CHAT_INPUT.
    decoy = FakeLocator(elements=[FakeElement(text="decoy", visible=True)])
    composer = FakeLocator(elements=[FakeElement(visible=True)])
    page = FakePage(
        url="https://notebooklm.google.com/notebook/abc",
        locators={
            "textarea:not([disabled])": decoy,  # the deliberately-excluded one
            S.CHAT_INPUT[0]: composer,
        },
    )
    client = client_factory(page=page, notebook_id="abc", authenticated=True)

    await client.send_message("payload")

    # The composer got the full interaction...
    assert composer.calls == [
        "wait_for",
        "click",
        ("fill", "payload"),
        ("press", "Enter"),
    ]
    # ...and the decoy was never touched.
    assert decoy.calls == []


@pytest.mark.asyncio
async def test_send_message_falls_through_to_second_selector(client_factory):
    """First CHAT_INPUT selector matches nothing visible; ``_find_first`` falls
    through to the second candidate, which is the one that gets used.
    """
    second = FakeLocator(elements=[FakeElement(visible=True)])
    page = FakePage(
        url="https://notebooklm.google.com/notebook/abc",
        locators={
            # S.CHAT_INPUT[0] intentionally absent -> empty match -> timeout.
            S.CHAT_INPUT[1]: second,
        },
    )
    client = client_factory(page=page, notebook_id="abc", authenticated=True)

    await client.send_message("payload")

    assert second.calls == [
        "wait_for",
        "click",
        ("fill", "payload"),
        ("press", "Enter"),
    ]
    # The first selector was probed before falling through.
    assert page.locator_calls[0] == S.CHAT_INPUT[0]
    assert S.CHAT_INPUT[1] in page.locator_calls


@pytest.mark.asyncio
async def test_send_message_press_error_raises_chaterror(client_factory):
    composer = FakeLocator(
        elements=[FakeElement(visible=True, raise_on={"press": PWError("detached")})]
    )
    page = FakePage(
        url="https://notebooklm.google.com/notebook/abc",
        locators={S.CHAT_INPUT[0]: composer},
    )
    client = client_factory(page=page, notebook_id="abc", authenticated=True)

    with pytest.raises(ChatError, match="Failed to submit message"):
        await client.send_message("hi")


@pytest.mark.asyncio
async def test_send_message_no_notebook_skips_navigation(client_factory):
    """No ``current_notebook_id`` -> ``_ensure_on_notebook`` returns early with
    no goto (covers the client.py:234-235 early-return), and the composer is
    still located and used.
    """
    composer = FakeLocator(elements=[FakeElement(visible=True)])
    page = FakePage(
        url="https://notebooklm.google.com",
        locators={S.CHAT_INPUT[0]: composer},
    )
    client = client_factory(page=page, authenticated=True)
    client.current_notebook_id = None

    await client.send_message("payload")

    assert page.goto_calls == []  # no navigation attempted
    assert composer.calls == [
        "wait_for",
        "click",
        ("fill", "payload"),
        ("press", "Enter"),
    ]


@pytest.mark.asyncio
async def test_send_message_navigates_when_off_notebook(client_factory):
    """When the page URL is not on the target notebook, ``_ensure_on_notebook``
    triggers a real navigation before the composer is used.
    """
    composer = FakeLocator(elements=[FakeElement(visible=True)])
    page = FakePage(
        url="https://notebooklm.google.com/somewhere-else",
        goto_url="https://notebooklm.google.com/notebook/abc",
        locators={S.CHAT_INPUT[0]: composer},
    )
    client = client_factory(page=page, notebook_id="abc", authenticated=True)

    await client.send_message("payload")

    assert page.goto_calls == ["https://notebooklm.google.com/notebook/abc"]
    assert composer.calls[0] == "wait_for"


# --------------------------------------------------------------------------- #
# get_response()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_response_requires_page():
    client = NotebookLMClient(ServerConfig())
    with pytest.raises(ChatError):
        await client.get_response()


@pytest.mark.asyncio
async def test_get_response_no_wait_returns_latest():
    """REAL ``_read_latest_response`` reads the newest bubble (no wait path)."""
    page = FakePage(
        selectors={S.RESPONSE[0]: [FakeElement(text="the latest answer")]},
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    result = await client.get_response(wait_for_completion=False)
    assert result == "the latest answer"


@pytest.mark.asyncio
async def test_get_response_empty_returns_placeholder():
    """No response bubbles -> REAL ``_read_latest_response`` returns "" ->
    placeholder.
    """
    page = FakePage(selectors={})
    client = NotebookLMClient(ServerConfig())
    client.page = page

    result = await client.get_response(wait_for_completion=False)
    assert result == "No response content found"


@pytest.mark.asyncio
async def test_get_response_wait_path_runs_real_stability_loop(no_sleep):
    """Drive the REAL ``_wait_until_idle`` + REAL ``_read_latest_response`` +
    REAL ``_is_thinking``:

    * the response text changes over the first polls, then stabilizes;
    * the thinking indicator is visible at first, then flips hidden.

    The loop must only return once thinking has cleared AND the text has been
    stable for ``response_stability_checks`` polls.
    """
    config = ServerConfig(response_stability_checks=2, streaming_timeout=60)
    client = NotebookLMClient(config)

    # Each call to page.locator() advances the shared poll counter by 1. Per
    # poll iteration of _wait_until_idle, locator() is called once for the
    # RESPONSE read and once (per visible THINKING selector probe) for thinking.
    # Use generous timelines that converge to a stable answer and a cleared
    # thinking indicator.
    response_text = [
        "Partial",  # poll 1
        "Partial answer",  # poll 2  (changed -> resets stable)
        "Final answer",  # poll 3  (changed -> resets stable)
        "Final answer",  # poll 4  (stable #1)  thinking still on early
        "Final answer",  # poll 5
        "Final answer",  # poll 6
        "Final answer",  # subsequent polls stick on last value
    ]
    # Thinking visible for the early polls, then hidden.
    thinking_visible = [True, True, True, True, False, False, False]

    page = FakePage(
        selectors={
            S.RESPONSE[0]: [FakeElement(text=response_text)],
            S.THINKING[0]: [FakeElement(visible=thinking_visible)],
        },
    )
    client.page = page

    result = await client.get_response(wait_for_completion=True)

    assert result == "Final answer"


@pytest.mark.asyncio
async def test_get_response_does_not_return_while_thinking(no_sleep):
    """Even with stable text, the loop must NOT return while the thinking
    indicator is still visible. It returns only after thinking clears.

    Kills a mutation that drops the ``not thinking`` guard: with stable text and
    ``response_stability_checks=1`` the stability count is satisfied by poll #2,
    so an implementation that ignored ``thinking`` would return then. The real
    loop must keep polling until ``thinking`` flips hidden at poll #5, producing
    strictly more RESPONSE reads.
    """
    config = ServerConfig(response_stability_checks=1, streaming_timeout=60)
    client = NotebookLMClient(config)

    # Text is stable from the very first poll (so the stability count of 1 is
    # met as soon as the second poll), but the thinking indicator stays visible
    # well past that point. Each poll iteration probes RESPONSE then THINKING, so
    # the THINKING check on poll-iteration K sees the (2*K)-th sequenced value;
    # keeping the timeline ``True`` through index 7 means thinking only clears on
    # poll-iteration #4. A correct loop therefore performs >= 4 RESPONSE reads,
    # while a mutation that ignores ``thinking`` returns at iteration #2 (only
    # 2 reads) -- killing it.
    thinking_timeline = [True] * 8 + [False]
    page = FakePage(
        selectors={
            S.RESPONSE[0]: [FakeElement(text="stable from the start")],
            S.THINKING[0]: [FakeElement(visible=thinking_timeline)],
        },
    )
    client.page = page

    await client.get_response(wait_for_completion=True)

    response_reads = [c for c in page.locator_calls if c == S.RESPONSE[0]]
    assert len(response_reads) >= 4


# --------------------------------------------------------------------------- #
# _wait_until_idle()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_wait_until_idle_times_out_without_error(no_sleep):
    """Stays 'thinking' the whole time; loop exits cleanly on deadline.

    Runs the REAL ``_read_latest_response`` and ``_is_thinking``.
    """
    config = ServerConfig(response_stability_checks=2)
    client = NotebookLMClient(config)
    page = FakePage(
        selectors={
            S.RESPONSE[0]: [FakeElement(text="still streaming")],
            S.THINKING[0]: [FakeElement(visible=True)],  # never settles
        },
    )
    client.page = page

    # Small budget so the deadline is hit immediately. Returns None, no raise.
    assert await client._wait_until_idle(max_wait=0) is None


@pytest.mark.asyncio
async def test_wait_until_idle_requires_stability_count(no_sleep):
    """With ``response_stability_checks=3`` and no thinking, the loop must see
    the SAME text three consecutive polls before returning. Proven by counting
    RESPONSE reads (>= 3).
    """
    config = ServerConfig(response_stability_checks=3, streaming_timeout=60)
    client = NotebookLMClient(config)
    page = FakePage(
        selectors={
            S.RESPONSE[0]: [FakeElement(text="done")],  # stable immediately
            # No THINKING selector -> _is_thinking is always False.
        },
    )
    client.page = page

    await client._wait_until_idle(max_wait=60)

    response_reads = [c for c in page.locator_calls if c == S.RESPONSE[0]]
    assert len(response_reads) >= 3


# --------------------------------------------------------------------------- #
# _read_latest_response()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_read_latest_response_picks_last_element():
    """Three matching elements; the LAST (index count-1) provides the text.

    This is the ``nth(count - 1)`` indexing -- a mutation to ``nth(0)`` reads
    "oldest" and fails this assertion.
    """
    elements = [
        FakeElement(text="oldest message"),
        FakeElement(text="middle message"),
        FakeElement(text="newest message"),
    ]
    page = FakePage(selectors={S.RESPONSE[0]: elements})
    client = NotebookLMClient(ServerConfig())
    client.page = page

    text = await client._read_latest_response()
    assert text == "newest message"


@pytest.mark.asyncio
async def test_read_latest_response_falls_through_selector_groups():
    """First RESPONSE group matches nothing; logic falls through to the second
    group and reads the last element there.
    """
    page = FakePage(
        selectors={
            # S.RESPONSE[0] absent -> count 0 -> skip.
            S.RESPONSE[1]: [
                FakeElement(text="from second group A"),
                FakeElement(text="from second group B"),
            ],
        },
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    text = await client._read_latest_response()
    assert text == "from second group B"


@pytest.mark.asyncio
async def test_read_latest_response_skips_blank_then_returns_next_group():
    """A matched element whose text is whitespace-only is not returned; the
    loop moves to the next group and returns its non-blank text.
    """
    page = FakePage(
        selectors={
            S.RESPONSE[0]: [FakeElement(text="   \n  ")],  # blank -> skipped
            S.RESPONSE[1]: [FakeElement(text="real content")],
        },
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    text = await client._read_latest_response()
    assert text == "real content"


@pytest.mark.asyncio
async def test_read_latest_response_returns_empty_when_none():
    """No selector matches anything -> "" (all default empty matches)."""
    page = FakePage(selectors={})
    client = NotebookLMClient(ServerConfig())
    client.page = page

    assert await client._read_latest_response() == ""


@pytest.mark.asyncio
async def test_read_latest_response_continues_on_playwright_error():
    """A selector group that raises a Playwright error mid-read is swallowed and
    the next group is tried (exercises the ``except PlaywrightError: continue``).
    """
    # The first group's element raises a real PlaywrightError on inner_text.
    raising = FakeElement(text="boom", raise_on={"inner_text": PWError("detached")})
    page = FakePage(
        selectors={
            S.RESPONSE[0]: [raising],
            S.RESPONSE[1]: [FakeElement(text="recovered")],
        },
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    assert await client._read_latest_response() == "recovered"


@pytest.mark.asyncio
async def test_read_latest_response_returns_empty_when_no_page():
    client = NotebookLMClient(ServerConfig())
    assert await client._read_latest_response() == ""


# --------------------------------------------------------------------------- #
# _is_thinking()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_is_thinking_true_when_indicator_visible():
    page = FakePage(selectors={S.THINKING[0]: [FakeElement(visible=True)]})
    client = NotebookLMClient(ServerConfig())
    client.page = page

    assert await client._is_thinking() is True


@pytest.mark.asyncio
async def test_is_thinking_falls_through_to_later_selector():
    """First THINKING selector has no visible node; a LATER selector does.
    The real loop must keep scanning rather than stop at the first group.
    """
    page = FakePage(
        selectors={
            # S.THINKING[0] absent -> not visible.
            S.THINKING[1]: [FakeElement(visible=True)],
        },
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    assert await client._is_thinking() is True


@pytest.mark.asyncio
async def test_is_thinking_false_when_no_indicator():
    page = FakePage(selectors={})  # all selectors match nothing visible
    client = NotebookLMClient(ServerConfig())
    client.page = page

    assert await client._is_thinking() is False


@pytest.mark.asyncio
async def test_is_thinking_continues_on_playwright_error():
    """A selector whose visibility probe raises is swallowed; scanning
    continues to a later selector that is visible.
    """
    raising = FakeElement(visible=True, raise_on={"is_visible": PWError("detached")})
    page = FakePage(
        selectors={
            S.THINKING[0]: [raising],
            S.THINKING[1]: [FakeElement(visible=True)],
        },
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    assert await client._is_thinking() is True


@pytest.mark.asyncio
async def test_is_thinking_false_when_no_page():
    client = NotebookLMClient(ServerConfig())
    assert await client._is_thinking() is False


# --------------------------------------------------------------------------- #
# _find_first() -- direct coverage of the real selector loop
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_find_first_returns_none_when_no_page():
    client = NotebookLMClient(ServerConfig())
    assert await client._find_first(S.CHAT_INPUT, timeout=1000) is None


@pytest.mark.asyncio
async def test_find_first_waits_for_visible_then_returns_it(no_sleep):
    """The real ``_find_first`` must ``wait_for`` each candidate and only return
    one that becomes visible -- not blindly return the first selector's locator.
    """
    visible = FakeLocator(elements=[FakeElement(visible=True)])
    page = FakePage(
        locators={
            # First candidate matches nothing -> wait_for times out.
            S.CHAT_INPUT[1]: visible,
        },
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    result = await client._find_first(S.CHAT_INPUT, timeout=4000)

    # _find_first returns ``locator.first`` (a scoped view sharing the same
    # element + call log as ``visible``).
    assert result is not None
    assert result.calls is visible.calls
    # It actually awaited visibility (not a blind return).
    assert "wait_for" in visible.calls
    # The first candidate was probed and timed out before falling through.
    assert page.locator_calls[0] == S.CHAT_INPUT[0]
    # It returned a view of the second (visible) candidate, not the first.
    assert page.locator_calls.index(S.CHAT_INPUT[0]) < page.locator_calls.index(
        S.CHAT_INPUT[1]
    )


@pytest.mark.asyncio
async def test_find_first_returns_none_when_nothing_visible(no_sleep):
    page = FakePage(locators={})  # nothing visible anywhere
    client = NotebookLMClient(ServerConfig())
    client.page = page

    assert await client._find_first(S.CHAT_INPUT, timeout=2000) is None
    # Every candidate was probed.
    for selector in S.CHAT_INPUT:
        assert selector in page.locator_calls


@pytest.mark.asyncio
async def test_find_first_swallows_generic_playwright_error(no_sleep):
    """A candidate whose ``wait_for`` raises a generic (non-timeout) Playwright
    error is swallowed; scanning continues to a visible candidate.
    """
    erroring = FakeLocator(
        elements=[FakeElement(visible=False, raise_on={"wait_for": PWError("boom")})]
    )
    visible = FakeLocator(elements=[FakeElement(visible=True)])
    page = FakePage(
        locators={
            S.CHAT_INPUT[0]: erroring,
            S.CHAT_INPUT[1]: visible,
        },
    )
    client = NotebookLMClient(ServerConfig())
    client.page = page

    result = await client._find_first(S.CHAT_INPUT, timeout=4000)
    assert result is not None
    assert result.calls is visible.calls
    assert "wait_for" in visible.calls


# --------------------------------------------------------------------------- #
# navigate_to_notebook()
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_navigate_to_notebook_requires_page():
    client = NotebookLMClient(ServerConfig())
    with pytest.raises(NavigationError):
        await client.navigate_to_notebook("xyz")


@pytest.mark.asyncio
async def test_navigate_to_notebook_success(client_factory):
    page = FakePage()  # goto echoes the requested URL
    client = client_factory(page=page, notebook_id="old")

    url = await client.navigate_to_notebook("new-id")

    assert client.current_notebook_id == "new-id"
    assert url == "https://notebooklm.google.com/notebook/new-id"
    assert page.goto_calls == ["https://notebooklm.google.com/notebook/new-id"]


@pytest.mark.asyncio
async def test_navigate_to_notebook_timeout_raises(client_factory):
    page = FakePage(goto_error=PWTimeout("nav timed out"))
    client = client_factory(page=page, notebook_id="old")

    with pytest.raises(NavigationError):
        await client.navigate_to_notebook("new-id")


# --------------------------------------------------------------------------- #
# close() / driver / is_authenticated
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_close_is_safe_with_no_page():
    client = NotebookLMClient(ServerConfig())
    client._is_authenticated = True

    await client.close()

    assert client._is_authenticated is False
    assert client.page is None


@pytest.mark.asyncio
async def test_close_shuts_down_and_resets(client_factory):
    page = FakePage()
    context = FakeContext(pages=[page])
    playwright = FakePlaywright()
    client = client_factory(page=page, authenticated=True)
    client.context = context
    client._playwright = playwright

    await client.close()

    assert context.closed is True
    assert playwright.stopped is True
    assert client.page is None
    assert client.context is None
    assert client._playwright is None
    assert client.is_authenticated is False


def test_driver_property_returns_page():
    client = NotebookLMClient(ServerConfig())
    assert client.driver is None
    page = FakePage()
    client.page = page
    assert client.driver is page
