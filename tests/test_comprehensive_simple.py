"""Comprehensive, deterministic unit tests (no real browser).

This suite was migrated off Selenium + undetected-chromedriver. The browser
engine is now Patchright async Playwright, so:

* ``selenium``/``undetected_chromedriver`` are uninstalled — nothing here may
  import them;
* the client is fully async (``start``/``authenticate``/``send_message``/
  ``get_response``/``navigate_to_notebook``/``close``) and exposes the Playwright
  ``Page`` via ``client.page`` (and the ``client.driver`` alias), whose URL is the
  ``page.url`` property;
* the removed Selenium internals (``_send_message_sync``, ``_authenticate_sync``,
  ``WebDriverWait`` …) are re-expressed against the new async API using small
  inline async fakes injected as ``client.page`` and monkeypatched helpers
  (``_find_first``, ``_read_latest_response``, ``_is_thinking``).

Only ``tests/test_integration.py`` is allowed to launch a real browser.
"""

import asyncio
import json
from types import MethodType

import pytest
from click.testing import CliRunner

import notebooklm_mcp.server as server_module
from notebooklm_mcp import cli as cli_module
from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import AuthConfig, ServerConfig
from notebooklm_mcp.exceptions import ChatError, NavigationError, NotebookLMError


# --------------------------------------------------------------------------- #
# Async Playwright fakes
# --------------------------------------------------------------------------- #
class FakeLocator:
    """Minimal stand-in for a Playwright ``Locator``."""

    def __init__(self, texts: list[str] | None = None, visible: bool = False):
        self._texts = texts or []
        self._visible = visible
        self.clicked = False
        self.filled: list[str] = []
        self.pressed: list[str] = []

    @property
    def first(self) -> "FakeLocator":
        return self

    def nth(self, _index: int) -> "FakeLocator":
        return self

    async def count(self) -> int:
        return len(self._texts)

    async def inner_text(self) -> str:
        return self._texts[-1] if self._texts else ""

    async def is_visible(self) -> bool:
        return self._visible

    async def wait_for(self, **_kwargs) -> None:
        return None

    async def click(self) -> None:
        self.clicked = True

    async def fill(self, value: str) -> None:
        self.filled.append(value)

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class FakePage:
    """Minimal stand-in for a Playwright ``Page``."""

    def __init__(self, url: str = "https://notebooklm.google.com/notebook/abc"):
        self._url = url
        self.goto_calls: list[str] = []
        self.default_timeout: int | None = None
        self.locators: dict[str, FakeLocator] = {}

    @property
    def url(self) -> str:
        return self._url

    def set_default_timeout(self, timeout: int) -> None:
        self.default_timeout = timeout

    async def goto(self, url: str, wait_until: str | None = None) -> None:
        self._url = url
        self.goto_calls.append(url)

    def locator(self, selector: str) -> FakeLocator:
        return self.locators.setdefault(selector, FakeLocator())


def make_client(**config_kwargs) -> NotebookLMClient:
    config = ServerConfig(**config_kwargs)
    return NotebookLMClient(config)


# --------------------------------------------------------------------------- #
# CLI tests (engine-agnostic, still valid)
# --------------------------------------------------------------------------- #
def test_cli_creates_and_updates_config(tmp_path):
    notebook_id = "123e4567-e89b-12d3-a456-426614174000"
    config_path = tmp_path / "notebooklm-config.json"

    cli_module.create_default_config(notebook_id, str(config_path))
    data = json.loads(config_path.read_text())
    assert data["default_notebook_id"] == notebook_id
    assert data["headless"] is False

    cli_module.update_config_to_headless(str(config_path))
    updated = json.loads(config_path.read_text())
    assert updated["headless"] is True


def test_cli_chat_command_flow(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    config = ServerConfig(default_notebook_id="abc")

    created = {}

    class ChatClient:
        def __init__(self, cfg):
            self.config = cfg
            self.calls = []
            created["client"] = self

        async def start(self):
            self.calls.append("start")

        async def authenticate(self):
            self.calls.append("authenticate")
            return True

        async def send_message(self, message):
            self.calls.append(("send", message))

        async def get_response(self):
            self.calls.append("response")
            return "ok"

        async def close(self):
            self.calls.append("close")

    def run_asyncio(coro):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(cli_module, "load_config", lambda path: config)
    monkeypatch.setattr(cli_module, "NotebookLMClient", ChatClient)
    monkeypatch.setattr(cli_module.asyncio, "run", run_asyncio)
    monkeypatch.setattr(cli_module.console, "print", lambda *args, **kwargs: None)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "chat", "--message", "hello"],
    )

    assert result.exit_code == 0
    client = created["client"]
    assert ("send", "hello") in client.calls
    assert "close" in client.calls


def test_extract_notebook_id_variants():
    notebook_id = "123e4567-e89b-12d3-a456-426614174000"
    assert (
        cli_module.extract_notebook_id(
            f"https://notebooklm.google.com/notebook/{notebook_id}"
        )
        == notebook_id
    )
    assert (
        cli_module.extract_notebook_id(f"notebooklm.google.com/notebook/{notebook_id}")
        == notebook_id
    )

    with pytest.raises(ValueError):
        cli_module.extract_notebook_id("https://example.com")


# --------------------------------------------------------------------------- #
# Client tests against the new async Patchright API
# --------------------------------------------------------------------------- #
def test_client_driver_alias_exposes_page():
    """``client.driver`` is the back-compat alias exposing the Playwright page."""
    client = make_client()
    page = FakePage()
    client.page = page
    assert client.driver is page
    assert client.driver.url == page.url
    assert client.is_authenticated is False


def test_client_authenticate_success(monkeypatch):
    client = make_client(default_notebook_id="abc")
    page = FakePage(url="https://notebooklm.google.com/notebook/abc")
    client.page = page

    async def fake_find_first(self, candidates, timeout):
        return FakeLocator(visible=True)

    monkeypatch.setattr(client, "_find_first", MethodType(fake_find_first, client))

    result = asyncio.run(client.authenticate())
    assert result is True
    assert client._is_authenticated is True
    # Authentication navigates to the target notebook URL.
    assert page.goto_calls and page.goto_calls[-1].endswith("/notebook/abc")


def test_client_authenticate_detects_signed_out():
    client = make_client(default_notebook_id="abc")

    class RedirectPage(FakePage):
        async def goto(self, url, wait_until=None):
            # Simulate Google bouncing us to the sign-in flow.
            self._url = "https://accounts.google.com/signin"
            self.goto_calls.append(url)

    client.page = RedirectPage()

    result = asyncio.run(client.authenticate())
    assert result is False
    assert client._is_authenticated is False


def test_client_authenticate_requires_started_browser():
    client = make_client(default_notebook_id="abc")
    client.page = None
    with pytest.raises(NotebookLMError):  # AuthenticationError subclasses this
        asyncio.run(client.authenticate())


def test_client_send_message_types_and_submits(monkeypatch):
    client = make_client(default_notebook_id="abc")
    page = FakePage(url="https://notebooklm.google.com/notebook/abc")
    client.page = page
    client._is_authenticated = True

    composer = FakeLocator(visible=True)

    async def fake_find_first(self, candidates, timeout):
        return composer

    monkeypatch.setattr(client, "_find_first", MethodType(fake_find_first, client))

    asyncio.run(client.send_message("hello world"))
    assert composer.clicked is True
    assert composer.filled == ["hello world"]
    assert composer.pressed == ["Enter"]


def test_client_send_message_requires_auth():
    client = make_client(default_notebook_id="abc")
    client.page = FakePage()
    client._is_authenticated = False
    with pytest.raises(ChatError):
        asyncio.run(client.send_message("hi"))


def test_client_send_message_missing_composer(monkeypatch):
    client = make_client(default_notebook_id="abc")
    page = FakePage(url="https://notebooklm.google.com/notebook/abc")
    client.page = page
    client._is_authenticated = True

    async def no_composer(self, candidates, timeout):
        return None

    monkeypatch.setattr(client, "_find_first", MethodType(no_composer, client))

    with pytest.raises(ChatError, match="Could not find chat input"):
        asyncio.run(client.send_message("hi"))


def test_client_get_response_quick(monkeypatch):
    client = make_client()
    client.page = FakePage()

    async def fake_read(self):
        return "the answer"

    monkeypatch.setattr(client, "_read_latest_response", MethodType(fake_read, client))

    result = asyncio.run(client.get_response(wait_for_completion=False))
    assert result == "the answer"


def test_client_get_response_empty_falls_back(monkeypatch):
    client = make_client()
    client.page = FakePage()

    async def fake_read(self):
        return ""

    monkeypatch.setattr(client, "_read_latest_response", MethodType(fake_read, client))

    result = asyncio.run(client.get_response(wait_for_completion=False))
    assert result == "No response content found"


def test_client_get_response_waits_until_idle(monkeypatch):
    client = make_client(response_stability_checks=1)
    client.page = FakePage()
    reads = iter(["partial", "final", "final", "final"])

    async def fake_read(self):
        return next(reads, "final")

    async def not_thinking(self):
        return False

    monkeypatch.setattr(client, "_read_latest_response", MethodType(fake_read, client))
    monkeypatch.setattr(client, "_is_thinking", MethodType(not_thinking, client))

    async def instant_sleep(_seconds):
        return None

    monkeypatch.setattr("notebooklm_mcp.client.asyncio.sleep", instant_sleep)

    result = asyncio.run(client.get_response(wait_for_completion=True, max_wait=5))
    assert result == "final"


def test_client_get_response_requires_browser():
    client = make_client()
    client.page = None
    with pytest.raises(ChatError):
        asyncio.run(client.get_response())


def test_client_read_latest_response_prefers_populated_selector():
    client = make_client()
    page = FakePage()
    # First selector empty, second has text — client should return the text.
    page.locators = {
        ".to-user-container .message-text-content": FakeLocator(texts=[]),
        "chat-message .to-user-container .message-text-content": FakeLocator(
            texts=["This is a substantially longer answer from NotebookLM"]
        ),
    }
    client.page = page

    result = asyncio.run(client._read_latest_response())
    assert "substantially longer" in result


def test_client_is_thinking_detects_visible_indicator():
    client = make_client()
    page = FakePage()
    page.locators = {"div.thinking-message": FakeLocator(visible=True)}
    client.page = page

    assert asyncio.run(client._is_thinking()) is True

    page.locators["div.thinking-message"]._visible = False
    for selector in ("div.thinking-message", ".thinking-message"):
        page.locators[selector] = FakeLocator(visible=False)
    assert asyncio.run(client._is_thinking()) is False


def test_client_navigate_to_notebook_updates_state():
    client = make_client()
    page = FakePage()
    client.page = page

    url = asyncio.run(client.navigate_to_notebook("xyz"))
    assert url.endswith("/notebook/xyz")
    assert client.current_notebook_id == "xyz"


def test_client_navigate_requires_started_browser():
    client = make_client()
    client.page = None
    with pytest.raises(NavigationError):
        asyncio.run(client.navigate_to_notebook("xyz"))


def test_client_close_is_idempotent():
    client = make_client()
    client.page = FakePage()
    client.context = None
    client._playwright = None
    client._is_authenticated = True

    asyncio.run(client.close())
    assert client.page is None
    assert client._is_authenticated is False

    # Second close must not raise (idempotent).
    asyncio.run(client.close())
    assert client.page is None


# --------------------------------------------------------------------------- #
# Server tests (lazy init, async DummyClient)
# --------------------------------------------------------------------------- #
class DummyFastMCP:
    def __init__(self, name: str):
        self.name = name
        self.tools: dict[str, callable] = {}
        self.run_calls = []

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    async def run_async(self, **kwargs):
        self.run_calls.append(kwargs)


# Unique sentinel so response assertions test real wiring (the server
# surfacing the client's value) rather than echoing a generic "response".
DUMMY_RESPONSE = "client-produced-answer-9d21"


class DummyClient:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.started = False
        self.closed = False
        self.authenticated = False
        self.sent_messages: list[str] = []
        self._is_authenticated = True
        self.navigated_to: list[str] = []
        self.responses = [DUMMY_RESPONSE]
        self.call_order: list[str] = []
        self.get_response_calls = 0

    async def start(self):
        self.started = True

    async def authenticate(self):
        self.authenticated = True
        return True

    async def close(self):
        self.closed = True

    async def send_message(self, message: str):
        self.sent_messages.append(message)
        self.call_order.append("send")

    async def get_response(self) -> str:
        self.get_response_calls += 1
        self.call_order.append("get")
        return self.responses[-1]

    async def navigate_to_notebook(self, notebook_id: str):
        self.navigated_to.append(notebook_id)
        self.config.default_notebook_id = notebook_id
        self.call_order.append("navigate")


@pytest.fixture(autouse=True)
def patch_fastmcp(monkeypatch):
    monkeypatch.setattr(server_module, "FastMCP", DummyFastMCP)


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    config = ServerConfig(default_notebook_id="abc")
    instance = server_module.NotebookLMFastMCP(config)
    dummy = DummyClient(config)
    instance.client = dummy

    async def noop(self):
        return self.client

    instance._ensure_client = MethodType(noop, instance)
    return instance, dummy


def test_server_healthcheck(server):
    server_instance, dummy = server
    result = asyncio.run(server_instance.app.tools["healthcheck"]())
    assert result["status"] == "healthy"
    dummy._is_authenticated = False
    result = asyncio.run(server_instance.app.tools["healthcheck"]())
    assert result["status"] == "needs_auth"


def test_server_chat_flow(server):
    server_instance, dummy = server
    request = server_module.SendMessageRequest(message="hi", wait_for_response=True)
    response = asyncio.run(server_instance.app.tools["send_chat_message"](request))
    assert response["status"] == "completed"
    assert dummy.sent_messages == ["hi"]
    # The server must surface the client's actual response (unique sentinel),
    # proving it isn't returning a hardcoded string.
    assert response["response"] == DUMMY_RESPONSE
    assert dummy.call_order == ["send", "get"]

    dummy.call_order.clear()
    chat_request = server_module.ChatRequest(message="hey", notebook_id="new")
    response = asyncio.run(
        server_instance.app.tools["chat_with_notebook"](chat_request)
    )
    assert response["notebook_id"] == "new"
    assert dummy.navigated_to == ["new"]
    assert response["response"] == DUMMY_RESPONSE
    # navigate must precede send which precedes read.
    assert dummy.call_order == ["navigate", "send", "get"]

    nav_request = server_module.NavigateRequest(notebook_id="abc")
    result = asyncio.run(server_instance.app.tools["navigate_to_notebook"](nav_request))
    assert result["status"] == "success"
    assert result["notebook_id"] == "abc"


def test_server_response_tools_wire_client_value(server):
    """get_chat_response and get_quick_response must both surface the client's
    real response value and each delegate to client.get_response() once."""
    server_instance, dummy = server

    chat = asyncio.run(
        server_instance.app.tools["get_chat_response"](
            server_module.GetResponseRequest(timeout=1)
        )
    )
    quick = asyncio.run(server_instance.app.tools["get_quick_response"]())

    assert chat["response"] == DUMMY_RESPONSE
    assert quick["response"] == DUMMY_RESPONSE
    assert chat["status"] == "success"
    assert quick["status"] == "success"
    assert dummy.get_response_calls == 2


def test_server_send_chat_no_wait_skips_get_response(server):
    """wait_for_response=False must send the message but never read a reply."""
    server_instance, dummy = server
    request = server_module.SendMessageRequest(message="hi", wait_for_response=False)
    response = asyncio.run(server_instance.app.tools["send_chat_message"](request))

    assert response["status"] == "sent"
    assert "response" not in response
    assert dummy.sent_messages == ["hi"]
    assert dummy.get_response_calls == 0
    assert dummy.call_order == ["send"]


def test_server_default_notebook_tools(server):
    server_instance, _ = server
    result = asyncio.run(server_instance.app.tools["get_default_notebook"]())
    assert result["notebook_id"] == "abc"

    request = server_module.SetNotebookRequest(notebook_id="xyz")
    result = asyncio.run(server_instance.app.tools["set_default_notebook"](request))
    assert result["new_notebook_id"] == "xyz"
    assert server_instance.config.default_notebook_id == "xyz"


def test_server_ensure_client_lazy_init(monkeypatch):
    """First tool call triggers start()+authenticate() exactly once."""
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    # engine="patchright" routes _build_client through the injectable
    # NotebookLMClient symbol (the DummyClient), not the RPC backend.
    instance = server_module.NotebookLMFastMCP(
        ServerConfig(default_notebook_id="abc", engine="patchright")
    )

    asyncio.run(instance._ensure_client())
    first_client = instance.client
    assert first_client.started is True
    assert first_client.authenticated is True

    asyncio.run(instance._ensure_client())
    assert instance.client is first_client  # not recreated


def test_server_ensure_client_error_resets(monkeypatch):
    """A failed init raises NotebookLMError and clears the client for retry."""

    class FailingClient(DummyClient):
        async def start(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(server_module, "NotebookLMClient", FailingClient)
    # engine="patchright" so the injectable FailingClient is built and its
    # start() raises deterministically (no RPC/browser bootstrap).
    instance = server_module.NotebookLMFastMCP(
        ServerConfig(default_notebook_id="abc", engine="patchright")
    )

    with pytest.raises(NotebookLMError, match="Client initialization failed"):
        asyncio.run(instance._ensure_client())
    assert instance.client is None


def test_server_start_binds_transport_without_browser(monkeypatch):
    """start() is lazy: it binds the transport and never touches the browser."""
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    instance = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    asyncio.run(instance.start(transport="http", host="0.0.0.0", port=9000))
    assert instance.app.run_calls[-1] == {
        "transport": "http",
        "host": "0.0.0.0",
        "port": 9000,
    }
    # No tool was called, so the browser client was never constructed.
    assert instance.client is None

    asyncio.run(instance.stop())  # nothing to close, must not raise


def test_server_start_transport_error(monkeypatch):
    """The start() error path fires when the transport layer itself fails."""
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    instance = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    async def boom(**_kwargs):
        raise RuntimeError("transport down")

    instance.app.run_async = boom

    with pytest.raises(NotebookLMError, match="Server startup failed"):
        asyncio.run(instance.start())


def test_server_stop_closes_client(server):
    server_instance, dummy = server
    asyncio.run(server_instance.stop())
    assert dummy.closed is True


def test_server_tool_error_paths(monkeypatch, server):
    server_instance, _ = server

    class FailingClient(DummyClient):
        async def send_message(self, message):
            raise RuntimeError("fail")

    server_instance.client = FailingClient(server_instance.config)

    with pytest.raises(NotebookLMError):
        asyncio.run(
            server_instance.app.tools["send_chat_message"](
                server_module.SendMessageRequest(message="oops")
            )
        )


# Keep AuthConfig referenced so config import is meaningful even if the smoke
# integration tier (which uses it) is skipped in headless CI.
def test_auth_config_defaults():
    cfg = ServerConfig(auth=AuthConfig(profile_dir="/tmp/x"))
    assert cfg.auth.profile_dir == "/tmp/x"
    assert cfg.auth.use_persistent_session is True
