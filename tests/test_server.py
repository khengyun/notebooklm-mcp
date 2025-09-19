import json
import asyncio
import sys
from types import MethodType, SimpleNamespace

import pytest
from starlette.middleware import Middleware

from notebooklm_mcp import server as server_module
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import NotebookLMError


class DummyFastMCP:
    def __init__(self, name):
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
    def __init__(self, config):
        self.config = config
        self.started = False
        self.closed = False
        self.sent_messages = []
        self._is_authenticated = True
        self.navigated_to = []

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def send_message(self, message):
        self.sent_messages.append(message)

    async def get_response(self):
        return "response"

    async def navigate_to_notebook(self, notebook_id):
        self.config.default_notebook_id = notebook_id
        self.navigated_to.append(notebook_id)


@pytest.fixture(autouse=True)
def patch_fastmcp(monkeypatch):
    monkeypatch.setattr(server_module, "FastMCP", DummyFastMCP)


@pytest.fixture(autouse=True)
def monitoring_spy(monkeypatch):
    calls: dict[str, list[int]] = {"setup": []}

    async def fake_periodic(interval: int) -> None:
        await asyncio.sleep(0)

    def fake_setup(port: int) -> None:
        calls.setdefault("setup", []).append(port)

    monkeypatch.setattr(server_module, "setup_monitoring", fake_setup)
    monkeypatch.setattr(
        server_module,
        "periodic_health_check",
        lambda interval: fake_periodic(interval),
    )

    return calls


def test_notebooklmfastmcp_registers_tools(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    config = ServerConfig(default_notebook_id="abc")
    server = server_module.NotebookLMFastMCP(config)

    assert server.app.name == "NotebookLM MCP Server v2"
    expected_tools = {
        "healthcheck",
        "send_chat_message",
        "get_chat_response",
        "get_quick_response",
        "chat_with_notebook",
        "navigate_to_notebook",
        "get_default_notebook",
        "set_default_notebook",
    }
    assert expected_tools.issubset(server.app.tools.keys())


@pytest.mark.asyncio
async def test_ensure_client_initializes_once(monkeypatch):
    created = []

    class TrackingClient(DummyClient):
        def __init__(self, config):
            super().__init__(config)
            created.append(self)

    monkeypatch.setattr(server_module, "NotebookLMClient", TrackingClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    await server._ensure_client()
    await server._ensure_client()

    assert len(created) == 1
    assert created[0].started is True


@pytest.mark.asyncio
async def test_ensure_client_errors_propagate(monkeypatch):
    class FailingClient(DummyClient):
        async def start(self):  # pragma: no cover - exercised for error branch
            raise RuntimeError("boom")

    monkeypatch.setattr(server_module, "NotebookLMClient", FailingClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    with pytest.raises(NotebookLMError, match="Client initialization failed"):
        await server._ensure_client()


@pytest.mark.asyncio
async def test_start_uses_transport(monkeypatch, monitoring_spy):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.config.allow_remote_access = True
    await server.start(transport="http", host="0.0.0.0", port=9000)

    assert server.app.run_calls[-1] == {
        "transport": "http",
        "host": "0.0.0.0",
        "port": 9000,
    }
    assert monitoring_spy["setup"] == [server.config.metrics_port]


@pytest.mark.asyncio
async def test_start_http_adds_api_key_middleware(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    config = ServerConfig(default_notebook_id="abc")
    config.allow_remote_access = True
    config.require_api_key = True
    config.api_keys = ["alpha", "beta"]
    server = server_module.NotebookLMFastMCP(config)

    await server.start(transport="http", host="0.0.0.0", port=9050)

    run_call = server.app.run_calls[-1]
    assert run_call["transport"] == "http"
    middleware_stack = run_call.get("middleware")
    assert isinstance(middleware_stack, list)
    assert len(middleware_stack) == 1
    middleware = middleware_stack[0]
    assert isinstance(middleware, Middleware)
    assert middleware.cls.__name__ == "APIKeyMiddleware"
    assert middleware.kwargs["api_keys"] == {"alpha", "beta"}
    assert middleware.kwargs["header"] == config.api_key_header


@pytest.mark.asyncio
async def test_start_http_remote_requires_flag(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    with pytest.raises(NotebookLMError, match="Remote access is disabled"):
        await server.start(transport="http", host="0.0.0.0", port=9100)


@pytest.mark.asyncio
async def test_start_remote_without_api_key_warns(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    warnings: list[str] = []

    def record_warning(message, *args):
        warnings.append(message % args if args else message)

    def record_info(*_args, **_kwargs):
        return None

    def record_error(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        server_module,
        "logger",
        SimpleNamespace(
            info=record_info,
            warning=record_warning,
            error=record_error,
        ),
    )

    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.config.allow_remote_access = True

    await server.start(transport="http", host="0.0.0.0", port=9150)

    assert any("API key protection" in message for message in warnings)


@pytest.mark.asyncio
async def test_start_without_metrics(monkeypatch, monitoring_spy):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    config = ServerConfig(default_notebook_id="abc")
    config.allow_remote_access = True
    config.enable_metrics = False
    server = server_module.NotebookLMFastMCP(config)

    await server.start(transport="http", host="0.0.0.0", port=9101)

    assert monitoring_spy["setup"] == []


@pytest.mark.asyncio
async def test_start_handles_errors(monkeypatch):
    class ExplodingClient(DummyClient):
        async def start(self):  # pragma: no cover - error branch
            raise RuntimeError("fail")

    monkeypatch.setattr(server_module, "NotebookLMClient", ExplodingClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    with pytest.raises(NotebookLMError, match="Server startup failed"):
        await server.start()


@pytest.mark.asyncio
async def test_stop_closes_client(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    await server._ensure_client()
    dummy = server.client

    await server.stop()
    assert dummy.closed is True
    assert server.client is None


@pytest.mark.asyncio
async def test_healthcheck_tool_reports_status(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    result = await server.app.tools["healthcheck"]()
    assert result["status"] == "unhealthy"

    dummy = DummyClient(server.config)
    server.client = dummy
    result = await server.app.tools["healthcheck"]()
    assert result["status"] == "healthy"


@pytest.mark.asyncio
async def test_send_chat_message_tool(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    dummy = DummyClient(server.config)
    server.client = dummy

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.SendMessageRequest(message="hi", wait_for_response=True)
    response = await server.app.tools["send_chat_message"](request)

    assert dummy.sent_messages == ["hi"]
    assert response["status"] == "completed"


@pytest.mark.asyncio
async def test_send_chat_message_tool_no_wait(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    dummy = DummyClient(server.config)
    server.client = dummy

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.SendMessageRequest(message="hi", wait_for_response=False)
    response = await server.app.tools["send_chat_message"](request)

    assert response["status"] == "sent"
    assert "response" not in response


@pytest.mark.asyncio
async def test_send_chat_message_tool_error(monkeypatch):
    class FailingClient(DummyClient):
        async def send_message(self, message):
            raise RuntimeError("fail")

    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.client = FailingClient(server.config)

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.SendMessageRequest(message="hi", wait_for_response=False)

    with pytest.raises(NotebookLMError):
        await server.app.tools["send_chat_message"](request)


@pytest.mark.asyncio
async def test_chat_with_notebook_tool(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    dummy = DummyClient(server.config)
    server.client = dummy

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.ChatRequest(message="hello", notebook_id="xyz")
    response = await server.app.tools["chat_with_notebook"](request)

    assert dummy.sent_messages == ["hello"]
    assert dummy.navigated_to == ["xyz"]
    assert response["notebook_id"] == "xyz"


@pytest.mark.asyncio
async def test_get_chat_response_and_quick_response(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    dummy = DummyClient(server.config)
    server.client = dummy

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.GetResponseRequest(timeout=1)

    chat_result = await server.app.tools["get_chat_response"](request)
    quick_result = await server.app.tools["get_quick_response"]()

    assert chat_result["response"] == "response"
    assert quick_result["response"] == "response"


@pytest.mark.asyncio
async def test_get_chat_response_error(monkeypatch):
    class FailingClient(DummyClient):
        async def get_response(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.client = FailingClient(server.config)

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.GetResponseRequest(timeout=1)

    with pytest.raises(NotebookLMError):
        await server.app.tools["get_chat_response"](request)


@pytest.mark.asyncio
async def test_quick_response_error(monkeypatch):
    class FailingClient(DummyClient):
        async def get_response(self):
            raise RuntimeError("quick-fail")

    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.client = FailingClient(server.config)

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)

    with pytest.raises(NotebookLMError):
        await server.app.tools["get_quick_response"]()


@pytest.mark.asyncio
async def test_get_and_set_default_notebook_tools(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    dummy = DummyClient(server.config)
    server.client = dummy

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)

    get_result = await server.app.tools["get_default_notebook"]()
    assert get_result["notebook_id"] == "abc"

    request = server_module.SetNotebookRequest(notebook_id="new-id")
    set_result = await server.app.tools["set_default_notebook"](request)
    assert set_result["new_notebook_id"] == "new-id"
    assert server.config.default_notebook_id == "new-id"


@pytest.mark.asyncio
async def test_navigate_to_notebook_tool_error(monkeypatch):
    class BadClient(DummyClient):
        async def navigate_to_notebook(self, notebook_id):
            raise RuntimeError("navigate-fail")

    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.client = BadClient(server.config)

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.NavigateRequest(notebook_id="xyz")

    with pytest.raises(NotebookLMError):
        await server.app.tools["navigate_to_notebook"](request)


@pytest.mark.asyncio
async def test_start_sse_transport(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    server.config.allow_remote_access = True
    await server.start(transport="sse", host="0.0.0.0", port=8080)

    assert server.app.run_calls[-1] == {
        "transport": "sse",
        "host": "0.0.0.0",
        "port": 8080,
    }


@pytest.mark.asyncio
async def test_start_stdio_transport(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    await server.start()

    assert server.app.run_calls[-1] == {"transport": "stdio"}


def test_create_fastmcp_server_loads_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"default_notebook_id": "xyz"}))

    server = server_module.create_fastmcp_server(str(config_path))

    assert isinstance(server, server_module.NotebookLMFastMCP)
    assert server.config.default_notebook_id == "xyz"


@pytest.mark.asyncio
async def test_healthcheck_tool_error(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    class ExplodingClient:
        def __getattr__(self, _name):
            raise RuntimeError("boom")

    server.client = ExplodingClient()

    result = await server.app.tools["healthcheck"]()
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_navigate_to_notebook_tool_success(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    dummy = DummyClient(server.config)
    server.client = dummy

    async def fake_ensure(self):
        return None

    server._ensure_client = MethodType(fake_ensure, server)
    request = server_module.NavigateRequest(notebook_id="xyz")
    result = await server.app.tools["navigate_to_notebook"](request)

    assert result["status"] == "success"
    assert dummy.navigated_to == ["xyz"]


@pytest.mark.asyncio
async def test_set_default_notebook_error(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    class ExplodingConfig(SimpleNamespace):
        def __setattr__(self, name, value):
            if name == "default_notebook_id" and hasattr(self, name):
                raise RuntimeError("fail")
            super().__setattr__(name, value)

    server.config = ExplodingConfig(default_notebook_id="abc")
    request = server_module.SetNotebookRequest(notebook_id="boom")

    with pytest.raises(NotebookLMError):
        await server.app.tools["set_default_notebook"](request)


@pytest.mark.asyncio
async def test_stop_handles_client_close_error(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    errors = []

    class FailingClient(DummyClient):
        async def close(self):
            raise RuntimeError("fail")

    server.client = FailingClient(server.config)
    monkeypatch.setattr(
        server_module,
        "logger",
        SimpleNamespace(
            info=lambda *_args, **_kwargs: None, error=lambda msg: errors.append(msg)
        ),
    )

    await server.stop()

    assert any("Error during server shutdown" in message for message in errors)


@pytest.mark.asyncio
async def test_main_requires_config_argument(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["notebooklm_mcp.server"])

    with pytest.raises(SystemExit) as exc:
        await server_module.main()

    assert exc.value.code == 1


@pytest.mark.asyncio
async def test_main_handles_keyboardinterrupt(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "config.json"])

    class KeyboardServer:
        async def start(self):
            raise KeyboardInterrupt

    logs = []
    monkeypatch.setattr(
        server_module, "create_fastmcp_server", lambda _cfg: KeyboardServer()
    )
    monkeypatch.setattr(
        server_module,
        "logger",
        SimpleNamespace(
            info=lambda msg: logs.append(("info", msg)),
            error=lambda msg: logs.append(("error", msg)),
        ),
    )

    await server_module.main()

    assert ("info", "Server stopped by user") in logs


@pytest.mark.asyncio
async def test_main_handles_general_exception(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "config.json"])

    class FailingServer:
        async def start(self):
            raise RuntimeError("boom")

    logs = []

    def fake_exit(code):
        raise SystemExit(code)

    monkeypatch.setattr(
        server_module, "create_fastmcp_server", lambda _cfg: FailingServer()
    )
    monkeypatch.setattr(
        server_module,
        "logger",
        SimpleNamespace(info=lambda msg: None, error=lambda msg: logs.append(msg)),
    )
    monkeypatch.setattr(sys, "exit", fake_exit)

    with pytest.raises(SystemExit) as exc:
        await server_module.main()

    assert exc.value.code == 1
    assert any("Server error" in message for message in logs)
