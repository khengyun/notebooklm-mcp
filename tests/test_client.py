import asyncio
from types import MethodType, SimpleNamespace

import pytest
from selenium.common.exceptions import TimeoutException

from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import AuthenticationError, ChatError, NavigationError


class ImmediateLoop:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def run_in_executor(self, _executor, func, *args):
        future = self._loop.create_future()
        try:
            result = func(*args)
        except Exception as exc:  # pragma: no cover - exercised in tests
            future.set_exception(exc)
        else:
            future.set_result(result)
        return future


class DummyElement:
    def __init__(self, text="", displayed=True):
        self.text = text
        self._displayed = displayed
        self.cleared = False
        self.sent = []

    def is_displayed(self):
        return self._displayed

    def clear(self):
        self.cleared = True

    def send_keys(self, value):
        self.sent.append(value)


class DummyDriver:
    def __init__(self):
        self.current_url = "https://notebooklm.google.com/notebook/original"
        self.calls = []
        self.elements = {}

    def set_page_load_timeout(self, timeout):
        self.calls.append(("timeout", timeout))

    def get(self, url):
        self.current_url = url
        self.calls.append(("get", url))

    def find_elements(self, _by, selector):
        return self.elements.get(selector, [])

    def quit(self):
        self.calls.append(("quit", None))


@pytest.fixture
def config(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    return ServerConfig(default_notebook_id="abc", auth=ServerConfig().auth)


def test_start_browser_uses_fallback(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()

    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", False, raising=False)

    def fake_start(self):
        self.driver = driver

    monkeypatch.setattr(
        client,
        "_start_regular_chrome",
        MethodType(lambda self: fake_start(self), client),
    )

    client._start_browser()

    assert client.driver is driver
    assert ("timeout", client.config.timeout) in driver.calls


@pytest.mark.asyncio
async def test_send_message_requires_authentication():
    client = NotebookLMClient(ServerConfig())
    client.driver = object()
    client._is_authenticated = False

    with pytest.raises(ChatError):
        await client.send_message("hello")


@pytest.mark.asyncio
async def test_send_message_uses_executor(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    client.driver = object()
    client._is_authenticated = True
    recorded = {}

    def fake_send(self, message):
        recorded["message"] = message

    monkeypatch.setattr(
        client,
        "_send_message_sync",
        MethodType(fake_send, client),
    )

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop",
        lambda: ImmediateLoop(loop),
    )

    await client.send_message("hi")
    assert recorded["message"] == "hi"


@pytest.mark.asyncio
async def test_get_response_quick(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    client.driver = object()
    monkeypatch.setattr(
        client,
        "_get_current_response",
        MethodType(lambda self: "response", client),
    )
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop",
        lambda: ImmediateLoop(loop),
    )

    result = await client.get_response(wait_for_completion=False)
    assert result == "response"


def test_get_current_response_prefers_longest():
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    driver.elements = {
        "[data-testid*='response']": [DummyElement("short")],
        "[class*='response']:last-child": [
            DummyElement(
                "This is a much longer response from NotebookLM that should be chosen"
            )
        ],
    }
    client.driver = driver

    result = client._get_current_response()
    assert "longer response" in result


def test_check_streaming_indicators_detects_visible():
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    indicator = DummyElement("", displayed=True)
    driver.elements = {
        "[class*='loading']": [indicator],
    }
    client.driver = driver

    assert client._check_streaming_indicators() is True


def test_navigate_to_notebook_sync_success(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    client.driver = driver

    class DummyWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, condition):
            return condition

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)

    url = client._navigate_to_notebook_sync("updated")
    assert "updated" in url
    assert client.current_notebook_id == "updated"


def test_navigate_to_notebook_sync_timeout(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    client.driver = driver

    class DummyWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, _condition):
            raise TimeoutException()

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)

    with pytest.raises(NavigationError):
        client._navigate_to_notebook_sync("bad")


@pytest.mark.asyncio
async def test_close_runs_quit(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    client.driver = driver
    client._is_authenticated = True

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop",
        lambda: ImmediateLoop(loop),
    )

    await client.close()

    assert client.driver is None
    assert client._is_authenticated is False
    assert ("quit", None) in driver.calls


def test_clean_response_text_removes_artifacts():
    client = NotebookLMClient(ServerConfig())
    messy = (
        "What is NotebookLM?\n"
        "NotebookLM is a tool designed to help organize research notes and generate answers from sources.\n"
        "thumb_up\nthumb_down"
    )

    cleaned = client._clean_response_text(messy)

    assert "thumb_up" not in cleaned
    assert "NotebookLM is a tool" in cleaned


def test_send_message_sync_success(monkeypatch):
    config = ServerConfig(default_notebook_id="abc")
    client = NotebookLMClient(config)
    driver = DummyDriver()
    driver.current_url = "https://notebooklm.google.com/notebook/abc"
    client.driver = driver
    element = DummyElement()

    class DummyWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, _condition):
            return element

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)
    monkeypatch.setattr(
        "selenium.webdriver.common.keys.Keys.RETURN",
        "RETURN",
        raising=False,
    )

    client._send_message_sync("hello")

    assert element.cleared is True
    assert "hello" in element.sent[0]
    assert "RETURN" in element.sent[-1]


def test_send_message_sync_no_element(monkeypatch):
    client = NotebookLMClient(ServerConfig(default_notebook_id="abc"))
    client.driver = DummyDriver()
    client.driver.current_url = "https://notebooklm.google.com/notebook/abc"

    class DummyWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, _condition):
            raise TimeoutException()

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)

    with pytest.raises(ChatError):
        client._send_message_sync("hello")


def test_wait_for_streaming_response(monkeypatch):
    config = ServerConfig(response_stability_checks=1)
    client = NotebookLMClient(config)

    monkeypatch.setattr(
        client,
        "_get_current_response",
        MethodType(lambda self: "Answer", client),
    )
    monkeypatch.setattr(
        client,
        "_check_streaming_indicators",
        MethodType(lambda self: False, client),
    )

    times = iter([0, 0.1, 0.2])
    monkeypatch.setattr("notebooklm_mcp.client.time.time", lambda: next(times, 1.0))
    monkeypatch.setattr("notebooklm_mcp.client.time.sleep", lambda _s: None)

    assert client._wait_for_streaming_response(max_wait=1) == "Answer"


@pytest.mark.asyncio
async def test_get_response_streaming(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    client.driver = object()

    monkeypatch.setattr(
        client,
        "_wait_for_streaming_response",
        MethodType(lambda self, _max_wait: "complete", client),
    )
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop",
        lambda: ImmediateLoop(loop),
    )

    result = await client.get_response(wait_for_completion=True)
    assert result == "complete"


@pytest.mark.asyncio
async def test_start_invokes_browser(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    called = {}

    def fake_start(self):
        called["start"] = True

    monkeypatch.setattr(
        client,
        "_start_browser",
        MethodType(lambda self: fake_start(self), client),
    )
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop",
        lambda: ImmediateLoop(loop),
    )

    await client.start()
    assert called["start"] is True


def test_get_current_response_fallback_text():
    client = NotebookLMClient(ServerConfig())

    class FallbackDriver(DummyDriver):
        def find_elements(self, _by, selector):
            if selector == "p, div, span":
                return [
                    SimpleNamespace(text="menu"),
                    SimpleNamespace(
                        text="This is a very detailed answer explaining NotebookLM capabilities in depth."
                    ),
                ]
            return []

    client.driver = FallbackDriver()
    assert "detailed answer" in client._get_current_response()


def test_start_browser_uses_undetected_driver(monkeypatch, tmp_path):
    config = ServerConfig()
    config.auth.use_persistent_session = True
    config.auth.profile_dir = str(tmp_path / "profile")
    client = NotebookLMClient(config)

    class DummyChromeOptions:
        def __init__(self):
            self.args = []

        def add_argument(self, arg):
            self.args.append(arg)

    class DummyChromeDriver:
        def __init__(self, options):
            self.options = options
            self.timeout = None

        def set_page_load_timeout(self, timeout):
            self.timeout = timeout

    class DummyUCModule:
        def ChromeOptions(self):
            return DummyChromeOptions()

        def Chrome(self, options=None, version_main=None):
            return DummyChromeDriver(options)

    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", True)
    monkeypatch.setattr("notebooklm_mcp.client.uc", DummyUCModule(), raising=False)

    client._start_browser()

    assert client.driver.timeout == config.timeout
    assert any("--user-data-dir" in arg for arg in client.driver.options.args)


def test_start_regular_chrome_configures_options(monkeypatch):
    config = ServerConfig(headless=True)
    client = NotebookLMClient(config)

    class DummyOptions:
        def __init__(self):
            self.arguments = []
            self.experimental = {}

        def add_argument(self, value):
            self.arguments.append(value)

        def add_experimental_option(self, name, value):
            self.experimental[name] = value

    class DummyDriver:
        def __init__(self, options=None):
            self.options = options
            self.executed = []
            self.timeout = None

        def execute_script(self, script):
            self.executed.append(script)

        def set_page_load_timeout(self, timeout):
            self.timeout = timeout

    monkeypatch.setattr("notebooklm_mcp.client.ChromeOptions", DummyOptions)
    monkeypatch.setattr(
        "notebooklm_mcp.client.webdriver.Chrome",
        lambda options=None: DummyDriver(options=options),
    )
    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", False)

    client._start_browser()

    assert "--no-sandbox" in client.driver.options.arguments
    assert "--headless=new" in client.driver.options.arguments
    assert any("webdriver" in call for call in client.driver.executed)
    assert client.driver.timeout == config.timeout


def test_start_browser_raises_when_driver_missing(monkeypatch):
    client = NotebookLMClient(ServerConfig())

    class DummyChromeOptions:
        def __init__(self):
            self.args = []

        def add_argument(self, _value):
            self.args.append(_value)

    class DummyUCModule:
        def ChromeOptions(self):
            return DummyChromeOptions()

        def Chrome(self, options=None, version_main=None):  # pragma: no cover - stub
            return None

    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", True)
    monkeypatch.setattr("notebooklm_mcp.client.uc", DummyUCModule(), raising=False)

    with pytest.raises(RuntimeError, match="Failed to initialize browser driver"):
        client._start_browser()


def test_authenticate_sync_success(monkeypatch):
    config = ServerConfig()
    client = NotebookLMClient(config)

    class DummyDriver:
        def __init__(self):
            self.current_url = (
                f"{config.base_url}/notebook/{config.default_notebook_id}"
            )

        def get(self, url):
            self.current_url = url

    class DummyWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, _condition):
            return True

    client.driver = DummyDriver()
    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)

    assert client._authenticate_sync() is True
    assert client._is_authenticated is True


def test_authenticate_sync_requires_manual_login(monkeypatch):
    config = ServerConfig(headless=False)
    client = NotebookLMClient(config)
    client.current_notebook_id = None

    class DummyDriver:
        def __init__(self):
            self.current_url = "https://accounts.google.com/signin"

        def get(self, url):
            self.current_url = "https://accounts.google.com/signin"

    class DummyWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, _condition):
            return True

    client.driver = DummyDriver()
    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)

    assert client._authenticate_sync() is False
    assert client._is_authenticated is False


def test_authenticate_sync_timeout(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    client.driver = SimpleNamespace(
        get=lambda _url: None, current_url="https://notebooklm.google.com"
    )

    class TimeoutWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, _condition):
            raise TimeoutException()

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", TimeoutWait)

    with pytest.raises(AuthenticationError):
        client._authenticate_sync()


@pytest.mark.asyncio
async def test_get_response_requires_driver():
    client = NotebookLMClient(ServerConfig())

    with pytest.raises(ChatError):
        await client.get_response()


def test_send_message_sync_submit_failure(monkeypatch):
    client = NotebookLMClient(ServerConfig(default_notebook_id="abc"))
    driver = DummyDriver()
    driver.current_url = "https://notebooklm.google.com/notebook/abc"
    client.driver = driver

    class DummyWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, _condition):
            class FailingInput:
                def __init__(self):
                    self.values = []

                def clear(self):
                    pass

                def send_keys(self, value):
                    self.values.append(value)
                    if value == "RETURN":
                        raise RuntimeError("fail")

            return FailingInput()

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)
    monkeypatch.setattr(
        "selenium.webdriver.common.keys.Keys.RETURN",
        "RETURN",
        raising=False,
    )

    with pytest.raises(ChatError, match="Failed to submit message"):
        client._send_message_sync("hello")


def test_wait_for_streaming_response_timeout(monkeypatch):
    client = NotebookLMClient(ServerConfig(response_stability_checks=2))

    monkeypatch.setattr(
        client,
        "_get_current_response",
        MethodType(lambda self: "", client),
    )
    monkeypatch.setattr(
        client,
        "_check_streaming_indicators",
        MethodType(lambda self: True, client),
    )

    sequence = iter([0.0, 0.5, 1.1])
    monkeypatch.setattr("notebooklm_mcp.client.time.time", lambda: next(sequence, 2.0))
    monkeypatch.setattr("notebooklm_mcp.client.time.sleep", lambda _s: None)

    result = client._wait_for_streaming_response(max_wait=1)
    assert "timeout" in result.lower()
