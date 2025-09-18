"""Legacy compatibility tests that exercise end-to-end flows in a compact form."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from selenium.common.exceptions import TimeoutException

import pytest
from click.testing import CliRunner

import notebooklm_mcp.cli as cli_module
from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import ChatError, NavigationError, NotebookLMError
from notebooklm_mcp.monitoring import (
    HealthChecker,
    MetricsCollector,
    request_timer,
    periodic_health_check,
    setup_logging,
    setup_monitoring,
)
from notebooklm_mcp.server import (
    ChatRequest,
    GetResponseRequest,
    NavigateRequest,
    NotebookLMFastMCP,
    create_fastmcp_server,
    SendMessageRequest,
    SetNotebookRequest,
)


class StubElement:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def clear(self) -> None:
        self.text = ""

    def send_keys(self, value: str) -> None:
        self.text += value

    def is_displayed(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True


class StubDriver:
    def __init__(self) -> None:
        self.current_url = "https://notebooklm.google.com/notebook/abc"
        self.executed: list[str] = []
        self.elements: dict[str, list[StubElement]] = {}
        self.visited: list[str] = []
        self.quit_called = False

    def execute_script(self, script: str, *_args: Any) -> None:
        self.executed.append(script)

    def find_elements(self, _by: str, selector: str) -> list[StubElement]:
        return self.elements.get(selector, [])

    def add_elements(self, selector: str, *elements: StubElement) -> None:
        self.elements[selector] = list(elements)

    def get(self, url: str) -> None:
        self.visited.append(url)
        self.current_url = url

    def quit(self) -> None:
        self.quit_called = True


def _run_coroutine_sync(coro: Any) -> Any:
    """Execute an async coroutine synchronously for CLI command tests."""

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_cli_server_command_invocation(
    cli_runner: CliRunner,
    config_file_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Running the server command should spin up the FastMCP wrapper."""

    config_path = config_file_factory({"default_notebook_id": "abc"})
    server_config = ServerConfig(default_notebook_id="abc")

    monkeypatch.setattr("notebooklm_mcp.cli.load_config", lambda _: server_config)

    started: dict[str, Any] = {}

    class DummyServer:
        def __init__(self, config: ServerConfig) -> None:
            self.config = config

        async def start(self, transport: str, host: str, port: int) -> None:
            started["params"] = (transport, host, port)

    monkeypatch.setattr("notebooklm_mcp.cli.NotebookLMFastMCP", DummyServer)
    monkeypatch.setattr("notebooklm_mcp.cli.asyncio.run", _run_coroutine_sync)
    monkeypatch.setattr(
        "notebooklm_mcp.cli.console.print", lambda *args, **kwargs: None
    )

    result = cli_runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "server",
            "--root-dir",
            str(tmp_path),
            "--transport",
            "stdio",
        ],
    )

    assert result.exit_code == 0
    assert started["params"] == ("stdio", "127.0.0.1", 8000)


def test_cli_chat_command_single_message(
    cli_runner: CliRunner, config_file_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chat command should orchestrate client calls for a single message."""

    config_path = config_file_factory({"default_notebook_id": "abc"})
    server_config = ServerConfig(default_notebook_id="abc")
    monkeypatch.setattr("notebooklm_mcp.cli.load_config", lambda _: server_config)

    created_clients: list[SimpleNamespace] = []

    class DummyClient:
        def __init__(self, config: ServerConfig) -> None:
            self.config = config
            self.calls: list[Any] = []
            created_clients.append(self)

        async def start(self) -> None:
            self.calls.append("start")

        async def authenticate(self) -> bool:
            self.calls.append("authenticate")
            return True

        async def send_message(self, message: str) -> None:
            self.calls.append(("send", message))

        async def get_response(self) -> str:
            self.calls.append("get_response")
            return "response"

        async def close(self) -> None:
            self.calls.append("close")

    monkeypatch.setattr("notebooklm_mcp.cli.NotebookLMClient", DummyClient)
    monkeypatch.setattr("notebooklm_mcp.cli.asyncio.run", _run_coroutine_sync)
    monkeypatch.setattr(
        "notebooklm_mcp.cli.console.print", lambda *args, **kwargs: None
    )

    result = cli_runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "chat", "--message", "Hello there"],
    )

    assert result.exit_code == 0
    assert created_clients, "CLI should instantiate a client"
    client = created_clients[0]
    assert client.calls[:3] == ["start", "authenticate", ("send", "Hello there")]
    assert "close" in client.calls


def test_client_message_and_response_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise synchronous client helpers without relying on Selenium."""

    config = ServerConfig(default_notebook_id="abc")
    client = NotebookLMClient(config)
    driver = StubDriver()
    element = StubElement()

    monkeypatch.setattr(
        "notebooklm_mcp.client.EC.element_to_be_clickable",
        lambda locator: (lambda _driver: element),
    )

    class DummyWait:
        def until(self, predicate):
            return predicate(None)

    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda *_args, **_kwargs: DummyWait(),
    )

    client.driver = driver
    client._is_authenticated = True

    client._send_message_sync("Hello NotebookLM")
    assert "Hello" in element.text

    driver.add_elements("[data-testid*='response']", StubElement())
    driver.elements["[data-testid*='response']"][0].text = "Final answer"
    assert "Final" in client._get_current_response()

    sequence = ["partial", "final"]

    def next_response() -> str:
        return sequence.pop(0) if sequence else "final"

    monkeypatch.setattr(client, "_get_current_response", next_response)
    monkeypatch.setattr(client, "_check_streaming_indicators", lambda: False)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    assert client._wait_for_streaming_response(3) == "final"


@pytest.mark.asyncio
async def test_server_tools_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    """FastMCP tools should delegate to the NotebookLM client."""

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    client_stub = SimpleNamespace(
        send_message=AsyncMock(),
        get_response=AsyncMock(return_value="ok"),
        navigate_to_notebook=AsyncMock(),
    )

    server.client = client_stub  # type: ignore[assignment]
    monkeypatch.setattr(server, "_ensure_client", AsyncMock())

    send_tool = server.app._tool_manager._tools["send_chat_message"].fn
    result = await send_tool(SendMessageRequest(message="hi", wait_for_response=True))
    assert result["status"] == "completed"
    client_stub.send_message.assert_awaited_once()
    client_stub.get_response.assert_awaited_once()

    response_tool = server.app._tool_manager._tools["get_chat_response"].fn
    result = await response_tool(GetResponseRequest())
    assert result["response"] == "ok"

    set_tool = server.app._tool_manager._tools["set_default_notebook"].fn
    outcome = await set_tool(SetNotebookRequest(notebook_id="new"))
    assert outcome["new_notebook_id"] == "new"

    chat_tool = server.app._tool_manager._tools["chat_with_notebook"].fn
    await chat_tool(ChatRequest(message="hello", notebook_id="xyz"))
    client_stub.navigate_to_notebook.assert_awaited_once_with("xyz")


def test_metrics_and_request_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Metrics collector should track basic counters and timings."""

    collector = MetricsCollector()
    monkeypatch.setattr("notebooklm_mcp.monitoring.metrics_collector", collector)

    collector.record_request(True, 0.5)
    collector.record_request(False, 1.0)
    collector.record_browser_restart()
    collector.record_auth_failure()
    collector.update_active_sessions(2)
    collector.update_system_metrics()

    async def run_timer() -> None:
        async with request_timer():
            await asyncio.sleep(0)

    _run_coroutine_sync(run_timer())

    metrics = collector.get_metrics()
    assert metrics["requests_total"] >= 3
    assert metrics["authentication_failures"] == 1
    assert metrics["active_sessions"] == 2


def test_metrics_prometheus_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Prometheus is available counters and gauges should initialize."""

    events: list[tuple[str, Any]] = []

    class DummyCounter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            events.append(("init", args[0]))

        def inc(self) -> None:
            events.append(("inc", self.__class__.__name__))

    class DummyHistogram(DummyCounter):
        def observe(self, value: float) -> None:  # type: ignore[override]
            events.append(("observe", value))

    class DummyGauge(DummyCounter):
        def set(self, value: float) -> None:  # type: ignore[override]
            events.append(("set", value))

    monkeypatch.setattr("notebooklm_mcp.monitoring.PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.Counter", DummyCounter, raising=False
    )
    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.Histogram", DummyHistogram, raising=False
    )
    monkeypatch.setattr("notebooklm_mcp.monitoring.Gauge", DummyGauge, raising=False)
    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.psutil.virtual_memory",
        lambda: SimpleNamespace(used=42, percent=10),
    )
    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.psutil.cpu_percent",
        lambda interval=None: 5,
    )

    collector = MetricsCollector()
    collector.record_request(True, 0.1)
    collector.record_request(False, 0.2)
    collector.record_browser_restart()
    collector.record_auth_failure()
    collector.update_active_sessions(3)
    collector.update_system_metrics()

    assert any(event[0] == "inc" for event in events)
    assert any(event[0] == "observe" for event in events)
    assert any(event[0] == "set" for event in events)


@pytest.mark.asyncio
async def test_health_checker_reports_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Health checker should surface authentication and browser status."""

    driver = SimpleNamespace(current_url="https://notebooklm.google.com/notebook/abc")
    client = SimpleNamespace(driver=driver, _is_authenticated=True)
    checker = HealthChecker(client)

    status = await checker.check_health()
    assert status.browser_status == "healthy"
    assert status.authentication_status == "authenticated"
    assert status.healthy is True


def test_client_browser_start_modes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover both undetected and regular Chrome startup branches."""

    config = ServerConfig(auth=ServerConfig().auth, headless=True)
    config.auth.profile_dir = str(tmp_path / "profile")
    client = NotebookLMClient(config)

    class DummyOptions:
        def __init__(self) -> None:
            self.arguments: list[str] = []

        def add_argument(self, argument: str) -> None:
            self.arguments.append(argument)

    undetected_driver = SimpleNamespace()

    def set_undetected_timeout(value: int) -> None:
        undetected_driver.timeout = value

    undetected_driver.set_page_load_timeout = set_undetected_timeout  # type: ignore[attr-defined]

    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", True)
    monkeypatch.setattr("notebooklm_mcp.client.uc.ChromeOptions", DummyOptions)
    monkeypatch.setattr(
        "notebooklm_mcp.client.uc.Chrome", lambda **_: undetected_driver
    )

    client._start_browser()
    assert client.driver is undetected_driver
    assert getattr(undetected_driver, "timeout", None) == config.timeout

    fallback_driver = SimpleNamespace()

    def set_timeout(value: int) -> None:
        fallback_driver.timeout = value

    def record_script(script: str) -> None:
        fallback_driver.script = script

    fallback_driver.set_page_load_timeout = set_timeout  # type: ignore[attr-defined]
    fallback_driver.execute_script = record_script  # type: ignore[attr-defined]

    monkeypatch.setattr("notebooklm_mcp.client.USE_UNDETECTED", False)
    monkeypatch.setattr(
        "notebooklm_mcp.client.webdriver.Chrome", lambda **_: fallback_driver
    )

    fallback_client = NotebookLMClient(config)
    fallback_client._start_browser()
    assert fallback_client.driver is fallback_driver
    assert getattr(fallback_driver, "timeout", None) == config.timeout
    assert "navigator" in fallback_driver.script


def test_client_authenticate_and_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Authentication helpers should update flags and return status."""

    config = ServerConfig(default_notebook_id="abc")
    client = NotebookLMClient(config)
    driver = StubDriver()

    driver.add_elements("body", StubElement("ready"))

    monkeypatch.setattr(
        "notebooklm_mcp.client.EC.presence_of_element_located",
        lambda *_args, **_kwargs: lambda _driver: True,
    )
    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda *_args, **_kwargs: SimpleNamespace(
            until=lambda condition: condition(driver)
        ),
    )

    client.driver = driver
    assert client._authenticate_sync() is True
    assert client._is_authenticated is True

    original_get = driver.get
    driver.get = lambda _url: setattr(
        driver, "current_url", "https://accounts.google.com/signin"
    )
    assert client._authenticate_sync() is False
    driver.get = original_get

    class DummyWait:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def until(self, predicate):
            return predicate(driver)

    monkeypatch.setattr("notebooklm_mcp.client.WebDriverWait", DummyWait)
    url = client._navigate_to_notebook_sync("target")
    assert "target" in url
    assert client.current_notebook_id == "target"


@pytest.mark.asyncio
async def test_server_quick_response_and_navigation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cover additional FastMCP tool behaviour."""

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    client_stub = SimpleNamespace(
        get_response=AsyncMock(return_value="quick"),
        navigate_to_notebook=AsyncMock(),
    )

    server.client = client_stub  # type: ignore[assignment]
    monkeypatch.setattr(server, "_ensure_client", AsyncMock())

    quick_tool = server.app._tool_manager._tools["get_quick_response"].fn
    quick = await quick_tool()
    assert quick["response"] == "quick"

    nav_tool = server.app._tool_manager._tools["navigate_to_notebook"].fn
    await nav_tool(NavigateRequest(notebook_id="xyz"))
    client_stub.navigate_to_notebook.assert_awaited_once_with("xyz")

    default_tool = server.app._tool_manager._tools["get_default_notebook"].fn
    info = await default_tool()
    assert info["notebook_id"] == "abc"

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"default_notebook_id": "abc"}))
    created = create_fastmcp_server(str(config_file))
    assert isinstance(created, NotebookLMFastMCP)


@pytest.mark.asyncio
async def test_server_ensure_client_and_healthcheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_ensure_client should initialize once and healthcheck should reflect state."""

    class DummyClient:
        def __init__(self, config: ServerConfig) -> None:
            self.config = config
            self.start = AsyncMock()
            self._is_authenticated = True
            self.driver = SimpleNamespace(current_url=config.base_url)
            self.close = AsyncMock()

    monkeypatch.setattr("notebooklm_mcp.server.NotebookLMClient", DummyClient)

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    health_tool = server.app._tool_manager._tools["healthcheck"].fn

    status = await health_tool()
    assert status["status"] == "unhealthy"

    await server._ensure_client()
    created_client = server.client
    await server._ensure_client()

    assert server.client is created_client
    assert created_client is not None
    created_client.start.assert_awaited_once()  # type: ignore[union-attr]

    status = await health_tool()
    assert status["status"] == "healthy"

    created_client._is_authenticated = False
    status = await health_tool()
    assert status["status"] == "needs_auth"

    class ExplodingClient:
        def __bool__(self) -> bool:
            return True

        def __getattr__(self, _name: str) -> Any:
            raise RuntimeError("boom")

    server.client = ExplodingClient()  # type: ignore[assignment]
    status = await health_tool()
    assert status["status"] == "error"


@pytest.mark.asyncio
async def test_server_ensure_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client creation failures should surface as NotebookLMError."""

    class FailingClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("fail")

    monkeypatch.setattr("notebooklm_mcp.server.NotebookLMClient", FailingClient)

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    with pytest.raises(NotebookLMError):
        await server._ensure_client()


@pytest.mark.asyncio
async def test_server_tool_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Errors inside tools should be wrapped as NotebookLMError."""

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(server, "_ensure_client", boom)
    send_tool = server.app._tool_manager._tools["send_chat_message"].fn

    with pytest.raises(NotebookLMError):
        await send_tool(SendMessageRequest(message="hi"))


@pytest.mark.asyncio
async def test_server_tool_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Navigation and default-notebook errors should propagate cleanly."""

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    failing_client = SimpleNamespace(
        navigate_to_notebook=AsyncMock(side_effect=RuntimeError("nav")),
    )

    server.client = failing_client  # type: ignore[assignment]
    monkeypatch.setattr(server, "_ensure_client", AsyncMock())

    nav_tool = server.app._tool_manager._tools["navigate_to_notebook"].fn
    with pytest.raises(NotebookLMError):
        await nav_tool(NavigateRequest(notebook_id="xyz"))

    class FailingConfig:
        headless = False

        def __init__(self) -> None:
            super().__setattr__("default_notebook_id", "abc")

        def __setattr__(self, name: str, value: Any) -> None:
            if name == "default_notebook_id" and hasattr(self, name):
                raise RuntimeError("boom")
            super().__setattr__(name, value)

    server.config = FailingConfig()  # type: ignore[assignment]
    set_tool = server.app._tool_manager._tools["set_default_notebook"].fn

    with pytest.raises(NotebookLMError):
        await set_tool(SetNotebookRequest(notebook_id="new"))


def test_request_timer_failure_and_setup_monitoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise monitoring helpers including Prometheus setup and error tracking."""

    collector = MetricsCollector()
    monkeypatch.setattr("notebooklm_mcp.monitoring.metrics_collector", collector)

    async def failing_timer() -> None:
        with pytest.raises(RuntimeError):
            async with request_timer():
                raise RuntimeError("boom")

    _run_coroutine_sync(failing_timer())
    assert collector.get_metrics()["requests_failed"] >= 1

    monkeypatch.setattr("notebooklm_mcp.monitoring.PROMETHEUS_AVAILABLE", True)
    recorded: dict[str, Any] = {}
    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.start_http_server",
        lambda port: recorded.setdefault("port", port),
        raising=False,
    )

    setup_monitoring(9100)
    assert recorded["port"] == 9100


def test_setup_monitoring_without_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Prometheus is unavailable a warning should be emitted."""

    warnings: list[str] = []
    monkeypatch.setattr("notebooklm_mcp.monitoring.PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr("notebooklm_mcp.monitoring.logger.warning", warnings.append)

    setup_monitoring(8123)

    assert warnings


def test_client_error_paths_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handle chat errors, streaming indicators, and graceful shutdown."""

    config = ServerConfig(default_notebook_id="abc")
    client = NotebookLMClient(config)

    with pytest.raises(ChatError):
        _run_coroutine_sync(client.send_message("hi"))

    client.driver = StubDriver()
    client._is_authenticated = True

    class FailingWait:
        def until(self, _predicate):
            raise TimeoutException()

    monkeypatch.setattr(
        "notebooklm_mcp.client.WebDriverWait",
        lambda *_args, **_kwargs: FailingWait(),
    )

    with pytest.raises(ChatError):
        client._send_message_sync("hello")

    messy = "Line\ncopy_all\nthumb_down\nFinal"
    cleaned = client._clean_response_text(messy)
    assert "copy_all" not in cleaned
    assert "Final" in cleaned

    client.driver.add_elements("[class*='loading']", StubElement())
    assert client._check_streaming_indicators() is True

    client.driver.elements.clear()
    assert client._check_streaming_indicators() is False

    _run_coroutine_sync(client.close())
    assert client.driver is None


def test_client_streaming_wait_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming wait should eventually return even when indicators persist."""

    client = NotebookLMClient(ServerConfig())
    client.driver = StubDriver()

    responses = ["partial", "partial"]
    monkeypatch.setattr(client, "_get_current_response", lambda: responses[0])
    monkeypatch.setattr(client, "_check_streaming_indicators", lambda: True)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    result = client._wait_for_streaming_response(1)
    assert "partial" in result


@pytest.mark.asyncio
async def test_server_start_and_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover the various transport branches of the server start routine."""

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    monkeypatch.setattr(server, "_ensure_client", AsyncMock())

    run_async = AsyncMock()
    server.app.run_async = run_async  # type: ignore[attr-defined]

    await server.start(transport="http", host="0.0.0.0", port=9000)
    run_async.assert_awaited_once_with(transport="http", host="0.0.0.0", port=9000)

    run_async.reset_mock()
    await server.start(transport="sse", host="0.0.0.0", port=9000)
    run_async.assert_awaited_once_with(transport="sse", host="0.0.0.0", port=9000)

    run_async.reset_mock()
    await server.start(transport="stdio")
    run_async.assert_awaited_once_with(transport="stdio")

    server.client = SimpleNamespace(close=AsyncMock())
    await server.stop()
    server.client.close.assert_awaited_once()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_server_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """If FastMCP run_async fails the error should be wrapped."""

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    monkeypatch.setattr(server, "_ensure_client", AsyncMock())

    failing = AsyncMock(side_effect=RuntimeError("boom"))
    server.app.run_async = failing  # type: ignore[attr-defined]

    with pytest.raises(NotebookLMError):
        await server.start(transport="http")

    failing.assert_awaited_once()


@pytest.mark.asyncio
async def test_server_stop_logs_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shutdown errors should be logged but not raised."""

    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.client = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("bad")))

    errors: list[str] = []
    monkeypatch.setattr(
        "notebooklm_mcp.server.logger.error", lambda msg: errors.append(str(msg))
    )

    await server.stop()

    assert errors and "bad" in errors[0]


def test_periodic_health_check_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the periodic health check loop updates metrics."""

    check_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.health_checker.check_health", check_mock
    )
    updates: list[str] = []
    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.metrics_collector.update_system_metrics",
        lambda: updates.append("update"),
    )

    async def aborting_sleep(_interval: int) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr("asyncio.sleep", aborting_sleep)

    with pytest.raises(asyncio.CancelledError):
        _run_coroutine_sync(periodic_health_check(1))

    assert updates


def test_periodic_health_check_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failures in the health check should be logged and ignored."""

    async def failing_check() -> None:
        raise RuntimeError("fail")

    monkeypatch.setattr(
        "notebooklm_mcp.monitoring.health_checker.check_health", failing_check
    )
    errors: list[str] = []
    monkeypatch.setattr("notebooklm_mcp.monitoring.logger.error", errors.append)

    async def aborting_sleep(_interval: int) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr("asyncio.sleep", aborting_sleep)

    with pytest.raises(asyncio.CancelledError):
        _run_coroutine_sync(periodic_health_check(1))

    assert any("fail" in entry for entry in errors)


def test_setup_logging_configures_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Structured logging should add handlers for stdout and files."""

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr("notebooklm_mcp.monitoring.logger.remove", lambda: None)

    def fake_add(*args: Any, **kwargs: Any) -> None:
        calls.append(("add", kwargs.get("level", "")))

    monkeypatch.setattr("notebooklm_mcp.monitoring.logger.add", fake_add)

    setup_logging(debug=True)

    levels = [level for action, level in calls if action == "add"]
    assert "DEBUG" in levels
    assert "ERROR" in levels
