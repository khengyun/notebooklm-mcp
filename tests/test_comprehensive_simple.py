import asyncio
import json
from types import MethodType, SimpleNamespace

import pytest
from click.testing import CliRunner
from selenium.common.exceptions import TimeoutException

import notebooklm_mcp.monitoring as monitoring
import notebooklm_mcp.server as server_module
from notebooklm_mcp import cli as cli_module
from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import ChatError, NavigationError, NotebookLMError


class DummyElement:
    def __init__(self, text: str = "", displayed: bool = True):
        self.text = text
        self._displayed = displayed
        self.cleared = False
        self.sent = []

    def is_displayed(self) -> bool:
        return self._displayed

    def clear(self) -> None:
        self.cleared = True

    def send_keys(self, value) -> None:
        self.sent.append(value)


class DummyDriver:
    def __init__(self):
        self.current_url = "https://notebooklm.google.com/notebook/original"
        self.calls: list[tuple[str, object]] = []
        self.elements: dict[str, list[DummyElement]] = {}
        self.chat_element = DummyElement()

    def set_page_load_timeout(self, timeout: int) -> None:
        self.calls.append(("timeout", timeout))

    def get(self, url: str) -> None:
        self.current_url = url
        self.calls.append(("get", url))

    def find_elements(self, _by, selector: str):
        return self.elements.get(selector, [])

    def quit(self) -> None:
        self.calls.append(("quit", None))


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


class DummyClient:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.started = False
        self.closed = False
        self.sent_messages: list[str] = []
        self._is_authenticated = True
        self.navigated_to: list[str] = []
        self.responses = ["response"]

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def send_message(self, message: str):
        self.sent_messages.append(message)

    async def get_response(self) -> str:
        return self.responses[-1]

    async def navigate_to_notebook(self, notebook_id: str):
        self.navigated_to.append(notebook_id)
        self.config.default_notebook_id = notebook_id


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


def test_client_authenticate_sets_flag(monkeypatch):
    client = NotebookLMClient(ServerConfig(default_notebook_id="abc"))
    driver = DummyDriver()
    driver.current_url = "https://notebooklm.google.com/notebook/abc"
    client.driver = driver

    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda driver, timeout: SimpleNamespace(until=lambda condition: True),
    )

    result = client._authenticate_sync()
    assert result is True
    assert client._is_authenticated is True
    assert any(call[0] == "get" for call in driver.calls)


def test_client_send_message_sync(monkeypatch):
    client = NotebookLMClient(ServerConfig(default_notebook_id="abc"))
    driver = DummyDriver()
    driver.current_url = "https://notebooklm.google.com/home"
    client.driver = driver
    client.current_notebook_id = "abc"

    monkeypatch.setattr(
        client,
        "_navigate_to_notebook_sync",
        MethodType(lambda self, notebook: driver.get(f"navigated/{notebook}"), client),
    )
    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda driver, timeout: SimpleNamespace(
            until=lambda condition: driver.chat_element
        ),
    )

    client._send_message_sync("hello world")
    assert driver.chat_element.cleared is True
    assert "hello world" in driver.chat_element.sent


def test_client_start_fallback(monkeypatch):
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


def test_client_send_message_sync_errors(monkeypatch):
    client = NotebookLMClient(ServerConfig(default_notebook_id="abc"))
    driver = DummyDriver()
    client.driver = driver
    client.current_notebook_id = None

    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda driver, timeout: SimpleNamespace(
            until=lambda condition: (_ for _ in ()).throw(TimeoutException())
        ),
    )

    with pytest.raises(ChatError):
        client._send_message_sync("hi")


@pytest.mark.asyncio
async def test_client_send_message_async(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    client.driver = object()
    client._is_authenticated = True
    recorded = {}

    monkeypatch.setattr(
        client,
        "_send_message_sync",
        MethodType(lambda self, message: recorded.setdefault("msg", message), client),
    )
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop", lambda: ImmediateLoop(loop)
    )

    await client.send_message("payload")
    assert recorded["msg"] == "payload"


@pytest.mark.asyncio
async def test_client_get_response_quick(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    client.driver = object()
    monkeypatch.setattr(
        client,
        "_get_current_response",
        MethodType(lambda self: "response", client),
    )
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop", lambda: ImmediateLoop(loop)
    )

    result = await client.get_response(wait_for_completion=False)
    assert result == "response"


def test_check_streaming_indicators_detects_visible():
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    visible = DummyElement("", displayed=True)
    driver.elements = {"[class*='loading']": [visible]}
    client.driver = driver

    assert client._check_streaming_indicators() is True
    visible._displayed = False
    assert client._check_streaming_indicators() is False


@pytest.mark.asyncio
async def test_client_navigation_and_close(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    client.driver = driver

    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda driver, timeout: SimpleNamespace(until=lambda condition: True),
    )

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        "notebooklm_mcp.client.asyncio.get_event_loop", lambda: ImmediateLoop(loop)
    )

    url = await client.navigate_to_notebook("xyz")
    assert url.endswith("/xyz")

    called = {}

    def fake_quit():
        called["quit"] = True

    driver.quit = fake_quit
    await client.close()
    assert called["quit"] is True
    assert client.driver is None


def test_get_current_response_prefers_longest():
    client = NotebookLMClient(ServerConfig())
    driver = DummyDriver()
    driver.elements = {
        "[data-testid*='response']": [DummyElement("short")],
        "[class*='response']:last-child": [
            DummyElement("This is a substantially longer answer from NotebookLM")
        ],
    }
    client.driver = driver

    result = client._get_current_response()
    assert "substantially longer" in result


def test_get_current_response_fallback_text():
    client = NotebookLMClient(ServerConfig())

    class FallbackDriver(DummyDriver):
        def __init__(self):
            super().__init__()
            self.elements = {}

        def find_elements(self, _by, selector):
            if selector == "p, div, span":
                return [
                    DummyElement("Ask about something"),
                    DummyElement(
                        "This is a comprehensive explanation that should be used as fallback"
                    ),
                ]
            return []

    client.driver = FallbackDriver()
    result = client._get_current_response()
    assert "comprehensive explanation" in result


def test_clean_response_text_removes_artifacts():
    client = NotebookLMClient(ServerConfig())
    messy = "Question?\ncopy_all\nthumb_down\nHere is the answer you need."
    cleaned = client._clean_response_text(messy)
    assert cleaned.startswith("Here is the answer")


def test_wait_for_streaming_response(monkeypatch):
    client = NotebookLMClient(ServerConfig(response_stability_checks=1))
    client.driver = object()
    responses = iter(["complete", "complete"])

    monkeypatch.setattr(
        client,
        "_get_current_response",
        MethodType(lambda self: next(responses), client),
    )
    monkeypatch.setattr(
        client,
        "_check_streaming_indicators",
        MethodType(lambda self: False, client),
    )
    monkeypatch.setattr("notebooklm_mcp.client.time.sleep", lambda _: None)

    result = client._wait_for_streaming_response(1)
    assert result == "complete"


def test_wait_for_streaming_response_timeout(monkeypatch):
    client = NotebookLMClient(ServerConfig())
    client.driver = object()
    monkeypatch.setattr(
        client,
        "_get_current_response",
        MethodType(lambda self: "", client),
    )
    monkeypatch.setattr("notebooklm_mcp.client.time.sleep", lambda _: None)

    result = client._wait_for_streaming_response(0)
    assert result == "Response timeout - no content retrieved"


def test_navigate_to_notebook_sync_success(monkeypatch):
    client = NotebookLMClient(ServerConfig(default_notebook_id="abc"))
    driver = DummyDriver()
    client.driver = driver

    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda driver, timeout: SimpleNamespace(until=lambda condition: True),
    )

    result = client._navigate_to_notebook_sync("xyz")
    assert result.endswith("/xyz")
    assert client.current_notebook_id == "xyz"


def test_navigate_to_notebook_sync_timeout(monkeypatch):
    client = NotebookLMClient(ServerConfig(default_notebook_id="abc"))
    driver = DummyDriver()
    client.driver = driver

    def failing_wait(driver, timeout):
        return SimpleNamespace(
            until=lambda condition: (_ for _ in ()).throw(TimeoutException())
        )

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", failing_wait)

    with pytest.raises(NavigationError):
        client._navigate_to_notebook_sync("xyz")


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
        return None

    instance._ensure_client = MethodType(noop, instance)
    return instance, dummy


@pytest.mark.asyncio
async def test_server_healthcheck(server):
    server_instance, dummy = server
    result = await server_instance.app.tools["healthcheck"]()
    assert result["status"] == "healthy"
    dummy._is_authenticated = False
    result = await server_instance.app.tools["healthcheck"]()
    assert result["status"] == "needs_auth"


@pytest.mark.asyncio
async def test_server_chat_flow(server):
    server_instance, dummy = server
    request = server_module.SendMessageRequest(message="hi", wait_for_response=True)
    response = await server_instance.app.tools["send_chat_message"](request)
    assert response["status"] == "completed"
    assert dummy.sent_messages == ["hi"]

    chat_request = server_module.ChatRequest(message="hey", notebook_id="new")
    response = await server_instance.app.tools["chat_with_notebook"](chat_request)
    assert response["notebook_id"] == "new"
    assert dummy.navigated_to == ["new"]

    nav_request = server_module.NavigateRequest(notebook_id="abc")
    result = await server_instance.app.tools["navigate_to_notebook"](nav_request)
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_server_default_notebook_tools(server):
    server_instance, _ = server
    result = await server_instance.app.tools["get_default_notebook"]()
    assert result["notebook_id"] == "abc"

    request = server_module.SetNotebookRequest(notebook_id="xyz")
    result = await server_instance.app.tools["set_default_notebook"](request)
    assert result["new_notebook_id"] == "xyz"
    assert server_instance.config.default_notebook_id == "xyz"


@pytest.mark.asyncio
async def test_server_start_and_stop(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    instance = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    await instance.start(transport="http", host="0.0.0.0", port=9000)
    assert instance.app.run_calls[-1] == {
        "transport": "http",
        "host": "0.0.0.0",
        "port": 9000,
    }

    await instance.stop()
    assert instance.client.closed is True


@pytest.mark.asyncio
async def test_server_start_error(monkeypatch):
    class ExplodingClient(DummyClient):
        async def start(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(server_module, "NotebookLMClient", ExplodingClient)
    instance = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    with pytest.raises(NotebookLMError, match="Server startup failed"):
        await instance.start()


@pytest.mark.asyncio
async def test_server_tool_error_paths(monkeypatch, server):
    server_instance, _ = server

    class FailingClient(DummyClient):
        async def send_message(self, message):
            raise RuntimeError("fail")

    server_instance.client = FailingClient(server_instance.config)

    with pytest.raises(NotebookLMError):
        await server_instance.app.tools["send_chat_message"](
            server_module.SendMessageRequest(message="oops")
        )


class DummyPsutil:
    def __init__(self, memory_percent=10.0, cpu_percent=20.0):
        self._memory_percent = memory_percent
        self._cpu_percent = cpu_percent

    def virtual_memory(self):
        return SimpleNamespace(percent=self._memory_percent, used=1024)

    def cpu_percent(self, interval=None):  # pragma: no cover - interval unused
        return self._cpu_percent


def test_metrics_collector_record_request():
    collector = monitoring.MetricsCollector()
    collector.record_request(True, 0.5)
    collector.record_request(False, 0.25)

    metrics = collector.get_metrics()
    assert metrics["requests_total"] == 2
    assert metrics["requests_success"] == 1
    assert metrics["requests_failed"] == 1
    assert metrics["average_response_time"] > 0


def test_metrics_collector_browser_and_auth():
    collector = monitoring.MetricsCollector()
    collector.record_browser_restart()
    collector.record_auth_failure()
    collector.update_active_sessions(3)

    metrics = collector.get_metrics()
    assert metrics["browser_restarts"] == 1
    assert metrics["authentication_failures"] == 1
    assert metrics["active_sessions"] == 3


def test_metrics_collector_with_prometheus(monkeypatch):
    class DummyMetric:
        def __init__(self, *_args, **_kwargs):
            self.events = []

        def inc(self):
            self.events.append(("inc", None))

        def observe(self, value):
            self.events.append(("observe", value))

        def set(self, value):
            self.events.append(("set", value))

    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(monitoring, "Counter", DummyMetric, raising=False)
    monkeypatch.setattr(monitoring, "Gauge", DummyMetric, raising=False)
    monkeypatch.setattr(monitoring, "Histogram", DummyMetric, raising=False)

    collector = monitoring.MetricsCollector()
    collector.record_request(True, 0.5)
    collector.record_request(False, 0.25)
    collector.record_browser_restart()
    collector.record_auth_failure()
    collector.update_active_sessions(3)

    monkeypatch.setattr(
        monitoring, "psutil", DummyPsutil(memory_percent=50.0, cpu_percent=45.0)
    )
    collector.update_system_metrics()

    assert collector.requests_counter.events
    assert any(event == ("set", 3) for event in collector.active_sessions_gauge.events)


@pytest.mark.asyncio
async def test_request_timer_success(monkeypatch):
    calls = []

    class DummyCollector:
        def record_request(self, success, response_time):
            calls.append((success, response_time))

    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())

    async with monitoring.request_timer():
        await asyncio.sleep(0)

    assert calls and calls[0][0] is True


@pytest.mark.asyncio
async def test_request_timer_failure(monkeypatch):
    calls = []

    class DummyCollector:
        def record_request(self, success, response_time):
            calls.append((success, response_time))

    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())

    with pytest.raises(RuntimeError):
        async with monitoring.request_timer():
            raise RuntimeError("boom")

    assert calls and calls[0][0] is False


@pytest.mark.asyncio
async def test_health_checker_reports_status(monkeypatch):
    dummy_psutil = DummyPsutil(memory_percent=40.0, cpu_percent=30.0)
    monkeypatch.setattr(monitoring, "psutil", dummy_psutil)

    client = SimpleNamespace(
        driver=SimpleNamespace(
            current_url="https://notebooklm.google.com/notebook/123"
        ),
        _is_authenticated=True,
    )

    checker = monitoring.HealthChecker(client)
    monitoring.metrics_collector.start_time = asyncio.get_event_loop().time()

    result = await checker.check_health()
    assert result.healthy is True
    assert result.browser_status == "healthy"
    assert result.authentication_status == "authenticated"


@pytest.mark.asyncio
async def test_health_checker_not_started(monkeypatch):
    dummy_psutil = DummyPsutil(memory_percent=20.0, cpu_percent=10.0)
    monkeypatch.setattr(monitoring, "psutil", dummy_psutil)

    client = SimpleNamespace(driver=None, _is_authenticated=False)
    checker = monitoring.HealthChecker(client)
    monitoring.metrics_collector.start_time = asyncio.get_event_loop().time()

    result = await checker.check_health()
    assert result.browser_status == "not_started"
    assert result.authentication_status == "not_authenticated"


def test_setup_monitoring_with_prometheus(monkeypatch):
    recorded = {}

    def fake_start(port):
        recorded["port"] = port

    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(monitoring, "start_http_server", fake_start, raising=False)

    monitoring.setup_monitoring(port=9001)
    assert recorded["port"] == 9001


def test_setup_monitoring_without_prometheus(monkeypatch):
    messages = []

    class DummyLogger:
        def warning(self, message):
            messages.append(message)

        def info(self, _message):  # pragma: no cover - unused
            pass

    monkeypatch.setattr(monitoring, "PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(monitoring, "logger", DummyLogger())

    monitoring.setup_monitoring(port=8002)
    assert any("metrics will not be exported" in msg for msg in messages)


@pytest.mark.asyncio
async def test_periodic_health_check_handles_cancel(monkeypatch):
    calls = {"health": 0, "metrics": 0}

    class DummyChecker:
        async def check_health(self):
            calls["health"] += 1

    class DummyCollector:
        def update_system_metrics(self):
            calls["metrics"] += 1

    async def fake_sleep(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(monitoring, "health_checker", DummyChecker())
    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await monitoring.periodic_health_check(interval=0)

    assert calls["health"] == 1
    assert calls["metrics"] == 1


@pytest.mark.asyncio
async def test_periodic_health_check_logs_error(monkeypatch):
    class BrokenChecker:
        async def check_health(self):
            raise RuntimeError("bad")

    class DummyCollector:
        def update_system_metrics(self):
            pass

    messages = []

    async def fake_sleep(_interval):
        raise asyncio.CancelledError

    monkeypatch.setattr(monitoring, "health_checker", BrokenChecker())
    monkeypatch.setattr(monitoring, "metrics_collector", DummyCollector())
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        monitoring, "logger", SimpleNamespace(error=lambda msg: messages.append(msg))
    )

    with pytest.raises(asyncio.CancelledError):
        await monitoring.periodic_health_check(interval=0)

    assert any("Periodic health check failed" in message for message in messages)


def test_setup_logging_configures_handlers(monkeypatch, tmp_path):
    calls = []

    class DummyLogger:
        def remove(self):
            calls.append(("remove", None))

        def add(self, *args, **kwargs):
            calls.append(("add", args, kwargs))

    monkeypatch.setattr(monitoring, "logger", DummyLogger())
    monkeypatch.chdir(tmp_path)

    monitoring.setup_logging(debug=True)

    actions = [entry[0] for entry in calls]
    assert actions.count("remove") == 1
    assert actions.count("add") >= 3


def test_setup_logging_info_level(monkeypatch, tmp_path):
    calls = []

    class DummyLogger:
        def remove(self):
            calls.append(("remove", None))

        def add(self, *args, **kwargs):
            calls.append(("add", args, kwargs))

    monkeypatch.setattr(monitoring, "logger", DummyLogger())
    monkeypatch.chdir(tmp_path)

    monitoring.setup_logging(debug=False)

    first_add = next(entry for entry in calls if entry[0] == "add")
    assert first_add[2]["level"] == "INFO"


@pytest.mark.asyncio
async def test_health_checker_handles_exception(monkeypatch):
    class BrokenPsutil:
        def virtual_memory(self):
            raise RuntimeError("fail")

        def cpu_percent(self, interval=None):
            return 0

    monkeypatch.setattr(monitoring, "psutil", BrokenPsutil())
    checker = monitoring.HealthChecker()
    result = await checker.check_health()
    assert result.healthy is False
    assert result.browser_status == "error"
