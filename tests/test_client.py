from __future__ import annotations

import asyncio
from dataclasses import dataclass
import types
from typing import List

import pytest

from notebooklm_mcp.client import NotebookLMClient, TimeoutException
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import AuthenticationError, ChatError, NavigationError


@dataclass
class FakeElement:
    text: str = ""
    displayed: bool = True
    enabled: bool = True

    def clear(self) -> None:
        self.text = ""

    def send_keys(self, value: str) -> None:
        self.text += value

    def is_displayed(self) -> bool:
        return self.displayed

    def is_enabled(self) -> bool:
        return self.enabled


class FakeDriver:
    def __init__(self) -> None:
        self.current_url = "https://notebooklm.google.com/notebook/default"
        self._store: dict[str, List[FakeElement]] = {}
        self.set_timeout: int | None = None
        self.quit_called = False
        self.visited: list[str] = []

    def set_page_load_timeout(self, value: int) -> None:
        self.set_timeout = value

    def get(self, url: str) -> None:
        self.visited.append(url)
        self.current_url = url

    def find_elements(self, _by: str, selector: str) -> List[FakeElement]:
        return self._store.get(selector, [])

    def add_elements(self, selector: str, *elements: FakeElement) -> None:
        self._store[selector] = list(elements)

    def execute_script(self, script: str) -> None:
        self.last_script = script

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture
def config(tmp_path) -> ServerConfig:
    profile = tmp_path / "profile"
    profile.mkdir()
    return ServerConfig(auth=ServerConfig().auth, default_notebook_id="abc", headless=True)


@pytest.fixture
def client(config: ServerConfig) -> NotebookLMClient:
    return NotebookLMClient(config)


def test_start_browser_uses_regular_chrome(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_driver = FakeDriver()

    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", False)
    monkeypatch.setattr("notebooklm_mcp.client.webdriver.Chrome", lambda **_: fake_driver)

    client._start_browser()

    assert client.driver is fake_driver
    assert fake_driver.set_timeout is not None


def test_start_browser_uses_undetected_when_available(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_driver = FakeDriver()

    class DummyOptions:
        def __init__(self) -> None:
            self.arguments: list[str] = []

        def add_argument(self, argument: str) -> None:
            self.arguments.append(argument)

    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", True)
    monkeypatch.setattr("notebooklm_mcp.client.uc.ChromeOptions", DummyOptions)
    monkeypatch.setattr("notebooklm_mcp.client.uc.Chrome", lambda **_: fake_driver)

    client._start_browser()
    assert client.driver is fake_driver


@pytest.mark.asyncio
async def test_start_async_uses_executor(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_driver = FakeDriver()

    def fake_start_browser() -> None:
        client.driver = fake_driver

    monkeypatch.setattr(client, "_start_browser", fake_start_browser)

    loop = asyncio.get_running_loop()

    class ImmediateLoop:
        def __init__(self, real_loop: asyncio.AbstractEventLoop) -> None:
            self._real_loop = real_loop

        def run_in_executor(self, _executor, func, *args):
            future = self._real_loop.create_future()
            try:
                result = func(*args)
            except Exception as exc:  # pragma: no cover - defensive
                future.set_exception(exc)
            else:
                future.set_result(result)
            return future

    monkeypatch.setattr("asyncio.get_event_loop", lambda: ImmediateLoop(loop))

    await client.start()
    assert client.driver is fake_driver


def test_authenticate_sync_sets_flag(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    driver.add_elements(("body"), FakeElement("ready"))
    client.driver = driver

    client._authenticate_sync()
    assert client._is_authenticated is True


def test_authenticate_sync_requires_login(client: NotebookLMClient) -> None:
    driver = FakeDriver()
    driver.current_url = "https://accounts.google.com/signin"
    driver.add_elements("body", FakeElement("ready"))
    driver.get = lambda url: None
    client.driver = driver

    result = client._authenticate_sync()
    assert result is False
    assert client._is_authenticated is False


@pytest.mark.asyncio
async def test_authenticate_raises_without_driver(client: NotebookLMClient) -> None:
    with pytest.raises(AuthenticationError):
        await client.authenticate()


def test_send_message_sync_populates_element(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    element = FakeElement()
    driver.find_elements = lambda _by, _selector: [element]
    driver.current_url = "https://notebooklm.google.com/notebook/abc"
    client.driver = driver
    client._is_authenticated = True

    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait", lambda *_args, **_kwargs: types.SimpleNamespace(
            until=lambda predicate: predicate(driver)
        )
    )

    client._send_message_sync("hello")
    assert element.text.startswith("hello")


@pytest.mark.asyncio
async def test_send_message_async_requires_auth(client: NotebookLMClient) -> None:
    with pytest.raises(ChatError):
        await client.send_message("hi")


def test_send_message_sync_raises_when_missing(client: NotebookLMClient) -> None:
    driver = FakeDriver()
    driver.current_url = "https://notebooklm.google.com/notebook/abc"
    client.driver = driver
    client._is_authenticated = True

    with pytest.raises(ChatError):
        client._send_message_sync("hi")


def test_wait_for_streaming_response_returns_final(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    client.driver = driver

    values = ["first", "final"]

    def fake_current_response() -> str:
        return values.pop(0) if values else "final"

    monkeypatch.setattr(client, "_get_current_response", fake_current_response)
    monkeypatch.setattr(client, "_check_streaming_indicators", lambda: False)
    monkeypatch.setattr("time.sleep", lambda _t: None)

    result = client._wait_for_streaming_response(3)
    assert result == "final"


def test_get_response_quick_returns_latest(client: NotebookLMClient) -> None:
    driver = FakeDriver()
    driver.add_elements("[data-testid*='response']", FakeElement("answer"))
    client.driver = driver

    result = client._get_current_response()
    assert "answer" in result


def test_get_current_response_fallback_text(client: NotebookLMClient) -> None:
    driver = FakeDriver()

    def find_elements(by: str, selector: str) -> List[FakeElement]:
        if selector == "p, div, span":
            long_text = "Here is the answer " + "detail " * 5
            return [FakeElement("Intro"), FakeElement(long_text)]
        return []

    driver.find_elements = find_elements  # type: ignore[assignment]
    client.driver = driver

    text = client._get_current_response()
    assert "Here is the answer" in text


def test_clean_response_text_removes_ui_artifacts(client: NotebookLMClient) -> None:
    messy = "Line 1\ncopy_all\nthumb_up\nUseful content"
    cleaned = client._clean_response_text(messy)
    assert "copy_all" not in cleaned
    assert "Useful content" in cleaned


def test_navigate_to_notebook_updates_state(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    client.driver = driver

    class DummyWait:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def until(self, predicate):
            return predicate(driver)

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)

    url = client._navigate_to_notebook_sync("target")
    assert "target" in url
    assert client.current_notebook_id == "target"


def test_navigate_to_notebook_timeout(client: NotebookLMClient, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    client.driver = driver

    class DummyWait:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def until(self, _predicate):
            raise TimeoutException("timeout")

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)

    with pytest.raises(NavigationError):
        client._navigate_to_notebook_sync("missing")


@pytest.mark.asyncio
async def test_close_shuts_down_driver(client: NotebookLMClient) -> None:
    driver = FakeDriver()
    client.driver = driver
    client._is_authenticated = True

    await client.close()
    assert client.driver is None
    assert client._is_authenticated is False
    assert driver.quit_called
