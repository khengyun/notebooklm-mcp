import json
import sys
from types import MethodType, SimpleNamespace

import pytest

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


# A distinctive sentinel that the production code can only surface by actually
# wiring the client's return value through. Asserting on this (rather than a
# generic "response") turns the response-field checks from tautologies into
# real wiring assertions: a mutation that hardcodes any other string is caught.
DUMMY_RESPONSE = "client-produced-answer-7f3a"


class DummyClient:
    def __init__(self, config):
        self.config = config
        self.started = False
        self.closed = False
        self.authenticated = False
        self.sent_messages = []
        self._is_authenticated = True
        self.navigated_to = []
        # Ordered log of orchestration calls so tests can assert the server
        # drives the client in the right sequence (navigate -> send -> read).
        self.call_order: list[str] = []
        self.get_response_calls = 0

    @property
    def is_authenticated(self):
        return self._is_authenticated

    async def start(self):
        self.started = True

    async def authenticate(self):
        self.authenticated = True
        return True

    async def close(self):
        self.closed = True

    async def send_message(self, message):
        self.sent_messages.append(message)
        self.call_order.append("send")

    async def get_response(self):
        self.get_response_calls += 1
        self.call_order.append("get")
        return DUMMY_RESPONSE

    async def navigate_to_notebook(self, notebook_id):
        self.config.default_notebook_id = notebook_id
        self.navigated_to.append(notebook_id)
        self.call_order.append("navigate")


@pytest.fixture(autouse=True)
def patch_fastmcp(monkeypatch):
    monkeypatch.setattr(server_module, "FastMCP", DummyFastMCP)


def _server_with_client(monkeypatch, client_cls=DummyClient):
    """Build a server with ``client_cls`` wired in and ``_ensure_client``
    stubbed to return it (no real initialization)."""
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    config = ServerConfig(default_notebook_id="abc")
    server = server_module.NotebookLMFastMCP(config)
    client = client_cls(config)
    server.client = client

    async def fake_ensure(self):
        return self.client

    server._ensure_client = MethodType(fake_ensure, server)
    return server, client


def test_notebooklmfastmcp_registers_tools(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    config = ServerConfig(default_notebook_id="abc")
    server = server_module.NotebookLMFastMCP(config)

    assert server.app.name == "NotebookLM MCP Server v2"
    expected_tools = {
        "healthcheck",
        "send_chat_message",
        "get_chat_response",
        "chat_with_notebook",
        "navigate_to_notebook",
        "get_default_notebook",
        "set_default_notebook",
    }
    assert expected_tools.issubset(server.app.tools.keys())
    # get_quick_response was merged into get_chat_response and must be gone.
    assert "get_quick_response" not in server.app.tools


@pytest.mark.asyncio
async def test_ensure_client_initializes_once(monkeypatch):
    created = []

    class TrackingClient(DummyClient):
        def __init__(self, config):
            super().__init__(config)
            created.append(self)

    # _ensure_client builds NotebookLMRPCClient (the injected TrackingClient).
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", TrackingClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    await server._ensure_client()
    await server._ensure_client()

    assert len(created) == 1
    assert created[0].started is True
    assert created[0].authenticated is True


@pytest.mark.asyncio
async def test_ensure_client_errors_propagate(monkeypatch):
    class FailingClient(DummyClient):
        async def start(self):  # pragma: no cover - exercised for error branch
            raise RuntimeError("boom")

    # The injected client's start() raises, so _ensure_client must wrap it.
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", FailingClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    with pytest.raises(NotebookLMError, match="Client initialization failed"):
        await server._ensure_client()

    # On failure the client must be reset so the next call retries cleanly.
    assert server.client is None


@pytest.mark.asyncio
async def test_start_uses_transport(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    await server.start(transport="http", host="0.0.0.0", port=9000)

    assert server.app.run_calls[-1] == {
        "transport": "http",
        "host": "0.0.0.0",
        "port": 9000,
    }


@pytest.mark.asyncio
async def test_start_does_not_init_client_eagerly(monkeypatch):
    """Lazy init: a broken client must NOT stop the transport binding.

    ``start()`` does not call ``_ensure_client`` — the client is created on the
    first tool call — so even a client whose ``start()`` explodes leaves the
    transport free to bind.
    """

    class ExplodingClient(DummyClient):
        async def start(self):  # pragma: no cover - must never be called by start()
            raise RuntimeError("fail")

    monkeypatch.setattr(server_module, "NotebookLMRPCClient", ExplodingClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    # Should NOT raise: the transport binds without touching the client.
    await server.start()

    assert server.app.run_calls[-1] == {"transport": "stdio"}
    # The client was never constructed because no tool was invoked.
    assert server.client is None


@pytest.mark.asyncio
async def test_start_handles_transport_errors(monkeypatch):
    """The ``start()`` error path fires when the transport itself fails."""
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    async def boom(**_kwargs):
        raise RuntimeError("transport down")

    server.app.run_async = boom

    with pytest.raises(NotebookLMError, match="Server startup failed"):
        await server.start()


@pytest.mark.asyncio
async def test_stop_closes_client(monkeypatch):
    # The real _ensure_client builds the injected DummyClient.
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    await server._ensure_client()

    await server.stop()
    assert server.client.closed is True


@pytest.mark.asyncio
async def test_healthcheck_tool_reports_status(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    # No client -> unhealthy, not authenticated.
    result = await server.app.tools["healthcheck"]()
    assert result["status"] == "unhealthy"
    assert result["authenticated"] is False

    # Authenticated client -> healthy, and the payload reflects real config.
    dummy = DummyClient(server.config)
    dummy._is_authenticated = True
    server.client = dummy
    result = await server.app.tools["healthcheck"]()
    assert result["status"] == "healthy"
    assert result["authenticated"] is True
    assert result["notebook_id"] == "abc"
    # headless defaults to False -> gui mode (proves config.headless is read).
    assert result["mode"] == "gui"

    # Client present but NOT authenticated -> needs_auth (distinct from both
    # the no-client and the healthy paths).
    dummy._is_authenticated = False
    result = await server.app.tools["healthcheck"]()
    assert result["status"] == "needs_auth"
    assert result["authenticated"] is False


@pytest.mark.asyncio
async def test_send_chat_message_tool(monkeypatch):
    server, dummy = _server_with_client(monkeypatch)
    response = await server.app.tools["send_chat_message"](
        message="hi", wait_for_response=True
    )

    assert dummy.sent_messages == ["hi"]
    assert response["status"] == "completed"
    # The echoed message must be exactly what we sent (not a fixed string).
    assert response["message"] == "hi"
    # wait_for_response=True must surface the client's real response via
    # get_response(); assert on the unique sentinel and the call ordering
    # (send happens before get).
    assert response["response"] == DUMMY_RESPONSE
    assert dummy.get_response_calls == 1
    assert dummy.call_order == ["send", "get"]


@pytest.mark.asyncio
async def test_send_chat_message_tool_no_wait(monkeypatch):
    server, dummy = _server_with_client(monkeypatch)
    response = await server.app.tools["send_chat_message"](
        message="hi", wait_for_response=False
    )

    assert response["status"] == "sent"
    assert "response" not in response
    # wait_for_response=False must NOT call get_response: the message is sent
    # but the server returns without reading a reply.
    assert dummy.sent_messages == ["hi"]
    assert dummy.get_response_calls == 0
    assert dummy.call_order == ["send"]


@pytest.mark.asyncio
async def test_send_chat_message_tool_error(monkeypatch):
    class FailingClient(DummyClient):
        async def send_message(self, message):
            raise RuntimeError("fail")

    server, _ = _server_with_client(monkeypatch, client_cls=FailingClient)

    with pytest.raises(NotebookLMError):
        await server.app.tools["send_chat_message"](
            message="hi", wait_for_response=False
        )


@pytest.mark.asyncio
async def test_chat_with_notebook_tool(monkeypatch):
    server, dummy = _server_with_client(monkeypatch)
    response = await server.app.tools["chat_with_notebook"](
        message="hello", notebook_id="xyz"
    )

    assert dummy.sent_messages == ["hello"]
    assert dummy.navigated_to == ["xyz"]
    assert response["notebook_id"] == "xyz"
    # Full orchestration contract: when a notebook_id is given the server must
    # navigate FIRST, then send, then read the response — in that exact order.
    assert dummy.call_order == ["navigate", "send", "get"]
    assert response["response"] == DUMMY_RESPONSE
    assert response["message"] == "hello"


@pytest.mark.asyncio
async def test_chat_with_notebook_no_navigation_when_id_absent(monkeypatch):
    """When no notebook_id is supplied the server must skip navigation and
    fall back to the configured default notebook id in its response."""
    server, dummy = _server_with_client(monkeypatch)
    response = await server.app.tools["chat_with_notebook"](
        message="hello", notebook_id=None
    )

    # No navigation happened; only send + read.
    assert dummy.navigated_to == []
    assert dummy.call_order == ["send", "get"]
    # The response falls back to the server's configured default notebook.
    assert response["notebook_id"] == "abc"
    assert response["response"] == DUMMY_RESPONSE


@pytest.mark.asyncio
async def test_get_chat_response(monkeypatch):
    server, dummy = _server_with_client(monkeypatch)
    chat_result = await server.app.tools["get_chat_response"]()

    # Assert on the unique sentinel: this proves the server surfaces the
    # client's actual return value (not a hardcoded "response" string) and
    # that the tool delegated to client.get_response() exactly once.
    assert chat_result["response"] == DUMMY_RESPONSE
    assert chat_result["status"] == "success"
    assert dummy.get_response_calls == 1


@pytest.mark.asyncio
async def test_get_chat_response_error(monkeypatch):
    class FailingClient(DummyClient):
        async def get_response(self):
            raise RuntimeError("boom")

    server, _ = _server_with_client(monkeypatch, client_cls=FailingClient)

    with pytest.raises(NotebookLMError):
        await server.app.tools["get_chat_response"]()


@pytest.mark.asyncio
async def test_get_and_set_default_notebook_tools(monkeypatch):
    server, _ = _server_with_client(monkeypatch)

    get_result = await server.app.tools["get_default_notebook"]()
    assert get_result["notebook_id"] == "abc"

    set_result = await server.app.tools["set_default_notebook"](notebook_id="new-id")
    assert set_result["new_notebook_id"] == "new-id"
    # The old id must be captured BEFORE the swap, proving the server records
    # the transition rather than echoing the new value twice.
    assert set_result["old_notebook_id"] == "abc"
    assert server.config.default_notebook_id == "new-id"


@pytest.mark.asyncio
async def test_chat_with_notebook_tool_error_wraps_exception(monkeypatch):
    """A failure inside chat_with_notebook must be wrapped as NotebookLMError."""

    class BadClient(DummyClient):
        async def send_message(self, message):
            raise RuntimeError("send blew up")

    server, _ = _server_with_client(monkeypatch, client_cls=BadClient)

    with pytest.raises(NotebookLMError, match="Chat interaction failed"):
        await server.app.tools["chat_with_notebook"](message="hello", notebook_id=None)


@pytest.mark.asyncio
async def test_navigate_to_notebook_tool_error(monkeypatch):
    class BadClient(DummyClient):
        async def navigate_to_notebook(self, notebook_id):
            raise RuntimeError("navigate-fail")

    server, _ = _server_with_client(monkeypatch, client_cls=BadClient)

    with pytest.raises(NotebookLMError):
        await server.app.tools["navigate_to_notebook"](notebook_id="xyz")


@pytest.mark.asyncio
async def test_start_sse_transport(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    await server.start(transport="sse", host="0.0.0.0", port=8080)

    assert server.app.run_calls[-1] == {
        "transport": "sse",
        "host": "0.0.0.0",
        "port": 8080,
    }


@pytest.mark.asyncio
async def test_start_stdio_transport(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
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
async def test_navigate_to_notebook_tool_success(monkeypatch):
    server, dummy = _server_with_client(monkeypatch)
    result = await server.app.tools["navigate_to_notebook"](notebook_id="xyz")

    assert result["status"] == "success"
    assert dummy.navigated_to == ["xyz"]


@pytest.mark.asyncio
async def test_set_default_notebook_error(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))

    class ExplodingConfig(SimpleNamespace):
        def __setattr__(self, name, value):
            if name == "default_notebook_id" and hasattr(self, name):
                raise RuntimeError("fail")
            super().__setattr__(name, value)

    server.config = ExplodingConfig(default_notebook_id="abc")

    with pytest.raises(NotebookLMError):
        await server.app.tools["set_default_notebook"](notebook_id="boom")


@pytest.mark.asyncio
async def test_stop_handles_client_close_error(monkeypatch):
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
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


# --------------------------------------------------------------------------- #
# Notebook / source management tools (RPC engine).
# --------------------------------------------------------------------------- #
# Unique sentinels so the management-tool assertions test real wiring (the
# server surfacing the client's value) rather than echoing a hardcoded payload.
NB_LIST = [{"id": "nb1", "title": "First", "emoji": "📓", "source_count": 2}]
NB_OBJ = {"id": "nb1", "title": "First", "emoji": "📓", "source_count": 2}
SRC_LIST = [{"id": "s1", "title": "Src", "type": "pdf", "status": "ready"}]
SRC_OBJ = {"id": "s1", "title": "Src", "type": "pdf", "status": "ready"}
SUMMARY = "an-ai-generated-summary-3b8f"


class ManagementClient(DummyClient):
    """An RPC-style client with management methods. Records every call."""

    def __init__(self, config):
        super().__init__(config)
        self.management_calls: list[tuple] = []

    async def list_notebooks(self):
        self.management_calls.append(("list_notebooks",))
        return NB_LIST

    async def create_notebook(self, title):
        self.management_calls.append(("create_notebook", title))
        return NB_OBJ

    async def rename_notebook(self, notebook_id, new_title):
        self.management_calls.append(("rename_notebook", notebook_id, new_title))
        return NB_OBJ

    async def delete_notebook(self, notebook_id):
        self.management_calls.append(("delete_notebook", notebook_id))

    async def get_notebook_summary(self, notebook_id):
        self.management_calls.append(("get_notebook_summary", notebook_id))
        return SUMMARY

    async def list_sources(self, notebook_id):
        self.management_calls.append(("list_sources", notebook_id))
        return SRC_LIST

    async def add_source_url(self, notebook_id, url):
        self.management_calls.append(("add_source_url", notebook_id, url))
        return SRC_OBJ

    async def add_source_text(self, notebook_id, title, text):
        self.management_calls.append(("add_source_text", notebook_id, title, text))
        return SRC_OBJ

    async def delete_source(self, notebook_id, source_id):
        self.management_calls.append(("delete_source", notebook_id, source_id))


def test_management_tools_registered(monkeypatch):
    """All 9 management tools must be registered on the app."""
    monkeypatch.setattr(server_module, "NotebookLMRPCClient", DummyClient)
    server = server_module.NotebookLMFastMCP(ServerConfig(default_notebook_id="abc"))
    expected = {
        "list_notebooks",
        "create_notebook",
        "rename_notebook",
        "delete_notebook",
        "get_notebook_summary",
        "list_sources",
        "add_source_url",
        "add_source_text",
        "delete_source",
    }
    assert expected.issubset(server.app.tools.keys())


@pytest.mark.asyncio
async def test_list_notebooks_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["list_notebooks"]()
    assert result["status"] == "success"
    assert result["count"] == 1
    # Surfaces the client's actual list (not a hardcoded payload).
    assert result["notebooks"] == NB_LIST
    assert client.management_calls == [("list_notebooks",)]


@pytest.mark.asyncio
async def test_create_notebook_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["create_notebook"](title="My NB")
    assert result["status"] == "success"
    assert result["notebook"] == NB_OBJ
    # The title flowed through to the client unchanged.
    assert client.management_calls == [("create_notebook", "My NB")]


@pytest.mark.asyncio
async def test_rename_notebook_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["rename_notebook"](
        notebook_id="nb1", new_title="Renamed"
    )
    assert result["notebook"] == NB_OBJ
    assert client.management_calls == [("rename_notebook", "nb1", "Renamed")]


@pytest.mark.asyncio
async def test_delete_notebook_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["delete_notebook"](notebook_id="nb1")
    assert result["status"] == "success"
    assert result["notebook_id"] == "nb1"
    assert client.management_calls == [("delete_notebook", "nb1")]


@pytest.mark.asyncio
async def test_get_notebook_summary_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["get_notebook_summary"](notebook_id="nb1")
    # Surfaces the client's unique summary string.
    assert result["summary"] == SUMMARY
    assert client.management_calls == [("get_notebook_summary", "nb1")]


@pytest.mark.asyncio
async def test_list_sources_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["list_sources"](notebook_id="nb1")
    assert result["count"] == 1
    assert result["sources"] == SRC_LIST
    assert client.management_calls == [("list_sources", "nb1")]


@pytest.mark.asyncio
async def test_add_source_url_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["add_source_url"](
        notebook_id="nb1", url="https://example.com"
    )
    assert result["source"] == SRC_OBJ
    assert client.management_calls == [("add_source_url", "nb1", "https://example.com")]


@pytest.mark.asyncio
async def test_add_source_text_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["add_source_text"](
        notebook_id="nb1", title="T", text="body"
    )
    assert result["source"] == SRC_OBJ
    assert client.management_calls == [("add_source_text", "nb1", "T", "body")]


@pytest.mark.asyncio
async def test_delete_source_tool(monkeypatch):
    server, client = _server_with_client(monkeypatch, client_cls=ManagementClient)
    result = await server.app.tools["delete_source"](notebook_id="nb1", source_id="s1")
    assert result["status"] == "success"
    assert result["notebook_id"] == "nb1"
    assert result["source_id"] == "s1"
    assert client.management_calls == [("delete_source", "nb1", "s1")]


@pytest.mark.asyncio
async def test_management_tool_wraps_client_error(monkeypatch):
    """A failure inside a management method is wrapped as NotebookLMError."""

    class FailingMgmt(ManagementClient):
        async def list_notebooks(self):
            raise RuntimeError("rpc down")

    server, _ = _server_with_client(monkeypatch, client_cls=FailingMgmt)
    with pytest.raises(NotebookLMError, match="Failed to list notebooks"):
        await server.app.tools["list_notebooks"]()
