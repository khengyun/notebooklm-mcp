from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import notebooklm_mcp.server as server_module
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import NotebookLMError
from notebooklm_mcp.server import (
    ChatRequest,
    GetResponseRequest,
    NavigateRequest,
    NotebookLMFastMCP,
    SendMessageRequest,
    SetNotebookRequest,
    create_fastmcp_server,
    main,
)


@pytest.fixture
def fastmcp_server() -> NotebookLMFastMCP:
    return NotebookLMFastMCP(ServerConfig(default_notebook_id="notebook-1"))


def test_tools_registered(fastmcp_server: NotebookLMFastMCP) -> None:
    tool_names = set(fastmcp_server.app._tool_manager._tools)
    expected = {
        "healthcheck",
        "send_chat_message",
        "get_chat_response",
        "get_quick_response",
        "chat_with_notebook",
        "navigate_to_notebook",
        "get_default_notebook",
        "set_default_notebook",
    }
    assert expected.issubset(tool_names)


@pytest.mark.asyncio
async def test_healthcheck_reports_authentication_state(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["healthcheck"].fn

    status = await tool()
    assert status["status"] == "unhealthy"

    fastmcp_server.client = SimpleNamespace(_is_authenticated=True)
    status = await tool()
    assert status["status"] == "healthy"
    assert status["authenticated"] is True


@pytest.mark.asyncio
async def test_healthcheck_reports_needs_auth_and_errors(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["healthcheck"].fn

    fastmcp_server.client = SimpleNamespace(_is_authenticated=False)
    status = await tool()
    assert status["status"] == "needs_auth"
    assert status["authenticated"] is False

    class ExplodingClient:
        def __bool__(self) -> bool:
            return True

        def __getattr__(self, name: str) -> None:  # pragma: no cover - debug helper
            raise RuntimeError("boom")

    fastmcp_server.client = ExplodingClient()
    status = await tool()
    assert status["status"] == "error"
    assert status["authenticated"] is False


@pytest.mark.asyncio
async def test_send_chat_message_tool(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["send_chat_message"].fn

    client = AsyncMock()
    client.get_response.return_value = "response"
    fastmcp_server.client = client
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    result = await tool(SendMessageRequest(message="hi", wait_for_response=True))

    fastmcp_server._ensure_client.assert_awaited_once()
    client.send_message.assert_awaited_once_with("hi")
    client.get_response.assert_awaited_once()
    assert result["status"] == "completed"
    assert result["response"] == "response"


@pytest.mark.asyncio
async def test_send_chat_message_without_wait(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["send_chat_message"].fn

    client = AsyncMock()
    fastmcp_server.client = client
    fastmcp_server.client.get_response = AsyncMock()  # type: ignore[assignment]
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    result = await tool(SendMessageRequest(message="hi", wait_for_response=False))

    fastmcp_server._ensure_client.assert_awaited_once()
    client.send_message.assert_awaited_once_with("hi")
    client.get_response.assert_not_called()
    assert result == {"status": "sent", "message": "hi"}


@pytest.mark.asyncio
async def test_send_chat_message_failure_wraps_error(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["send_chat_message"].fn

    async def fail():
        raise RuntimeError("boom")

    monkeypatch.setattr(fastmcp_server, "_ensure_client", fail)

    with pytest.raises(NotebookLMError):
        await tool(SendMessageRequest(message="hi"))


@pytest.mark.asyncio
async def test_get_chat_response(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["get_chat_response"].fn

    client = AsyncMock()
    client.get_response.return_value = "latest"
    fastmcp_server.client = client
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    result = await tool(GetResponseRequest(timeout=12))

    fastmcp_server._ensure_client.assert_awaited_once()
    client.get_response.assert_awaited_once()
    assert result["response"] == "latest"


@pytest.mark.asyncio
async def test_get_chat_response_failure(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["get_chat_response"].fn

    async def fail() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(fastmcp_server, "_ensure_client", fail)

    with pytest.raises(NotebookLMError) as exc:
        await tool(GetResponseRequest())

    assert "Failed to get response" in str(exc.value)


@pytest.mark.asyncio
async def test_get_quick_response(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["get_quick_response"].fn
    fastmcp_server.client = AsyncMock(get_response=AsyncMock(return_value="hello"))
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    result = await tool()
    assert result["response"] == "hello"


@pytest.mark.asyncio
async def test_get_quick_response_failure(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["get_quick_response"].fn
    client = AsyncMock()
    client.get_response.side_effect = RuntimeError("fail")
    fastmcp_server.client = client
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    with pytest.raises(NotebookLMError) as exc:
        await tool()

    assert "Failed to get quick response" in str(exc.value)


@pytest.mark.asyncio
async def test_chat_with_notebook_switches_notebooks(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["chat_with_notebook"].fn
    client = AsyncMock()
    fastmcp_server.client = client
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    await tool(ChatRequest(message="hi", notebook_id="other"))

    client.navigate_to_notebook.assert_awaited_once_with("other")
    client.send_message.assert_awaited_once()
    client.get_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_navigate_to_notebook_tool(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["navigate_to_notebook"].fn
    client = AsyncMock()
    fastmcp_server.client = client
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    result = await tool(SetNotebookRequest(notebook_id="target"))
    client.navigate_to_notebook.assert_awaited_once_with("target")
    assert result["notebook_id"] == "target"


@pytest.mark.asyncio
async def test_chat_with_notebook_failure(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["chat_with_notebook"].fn
    client = AsyncMock()
    client.send_message.side_effect = RuntimeError("fail")
    fastmcp_server.client = client
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    with pytest.raises(NotebookLMError) as exc:
        await tool(ChatRequest(message="hi", notebook_id="other"))

    assert "Chat interaction failed" in str(exc.value)


@pytest.mark.asyncio
async def test_navigate_to_notebook_failure(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["navigate_to_notebook"].fn
    client = AsyncMock()
    client.navigate_to_notebook.side_effect = RuntimeError("fail")
    fastmcp_server.client = client
    monkeypatch.setattr(fastmcp_server, "_ensure_client", AsyncMock())

    with pytest.raises(NotebookLMError) as exc:
        await tool(NavigateRequest(notebook_id="target"))

    assert "Failed to navigate" in str(exc.value)


@pytest.mark.asyncio
async def test_set_default_notebook_updates_config(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["set_default_notebook"].fn

    result = await tool(SetNotebookRequest(notebook_id="new"))
    assert fastmcp_server.config.default_notebook_id == "new"
    assert result["new_notebook_id"] == "new"


@pytest.mark.asyncio
async def test_set_default_notebook_failure(
    fastmcp_server: NotebookLMFastMCP,
) -> None:
    tool = fastmcp_server.app._tool_manager._tools["set_default_notebook"].fn

    class ImmutableConfig(ServerConfig):
        def __setattr__(self, name, value):
            if name == "default_notebook_id" and name in self.__dict__:
                raise RuntimeError("locked")
            super().__setattr__(name, value)

    fastmcp_server.config = ImmutableConfig(default_notebook_id="existing")

    with pytest.raises(NotebookLMError) as exc:
        await tool(SetNotebookRequest(notebook_id="new"))

    assert "Failed to set default notebook" in str(exc.value)


@pytest.mark.asyncio
async def test_ensure_client_initializes_once(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: dict[str, int] = {"init": 0, "start": 0}

    class DummyClient:
        def __init__(self, config: ServerConfig) -> None:
            created["init"] += 1
            self.config = config
            self.started = False

        async def start(self) -> None:
            created["start"] += 1
            self.started = True

        async def close(self) -> None:  # pragma: no cover - helper for compatibility
            pass

    monkeypatch.setattr("notebooklm_mcp.server.NotebookLMClient", DummyClient)

    await fastmcp_server._ensure_client()
    assert isinstance(fastmcp_server.client, DummyClient)
    assert created == {"init": 1, "start": 1}

    await fastmcp_server._ensure_client()
    assert created == {"init": 1, "start": 1}


@pytest.mark.asyncio
async def test_ensure_client_failure_wraps_error(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingClient:
        def __init__(self, config: ServerConfig) -> None:
            self.config = config

        async def start(self) -> None:
            raise RuntimeError("broken start")

    monkeypatch.setattr("notebooklm_mcp.server.NotebookLMClient", FailingClient)

    with pytest.raises(NotebookLMError) as exc:
        await fastmcp_server._ensure_client()

    assert "Client initialization failed" in str(exc.value)


@pytest.mark.asyncio
async def test_start_runs_transport(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ensure_client():
        fastmcp_server.client = AsyncMock()

    monkeypatch.setattr(fastmcp_server, "_ensure_client", ensure_client)
    run_async = AsyncMock()
    fastmcp_server.app.run_async = run_async  # type: ignore[assignment]

    await fastmcp_server.start(transport="http", host="0.0.0.0", port=9999)

    run_async.assert_awaited_once_with(transport="http", host="0.0.0.0", port=9999)


@pytest.mark.asyncio
async def test_start_stdio_transport(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ensure_client():
        fastmcp_server.client = AsyncMock()

    monkeypatch.setattr(fastmcp_server, "_ensure_client", ensure_client)
    run_async = AsyncMock()
    fastmcp_server.app.run_async = run_async  # type: ignore[assignment]

    await fastmcp_server.start()
    run_async.assert_awaited_once_with(transport="stdio")


@pytest.mark.asyncio
async def test_start_sse_transport(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ensure_client():
        fastmcp_server.client = AsyncMock()

    monkeypatch.setattr(fastmcp_server, "_ensure_client", ensure_client)
    run_async = AsyncMock()
    fastmcp_server.app.run_async = run_async  # type: ignore[assignment]

    await fastmcp_server.start(transport="sse", host="0.0.0.0", port=8888)
    run_async.assert_awaited_once_with(transport="sse", host="0.0.0.0", port=8888)


@pytest.mark.asyncio
async def test_start_raises_notebooklm_error(
    fastmcp_server: NotebookLMFastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_ensure() -> None:
        raise RuntimeError("ensure failure")

    monkeypatch.setattr(fastmcp_server, "_ensure_client", failing_ensure)

    with pytest.raises(NotebookLMError) as exc:
        await fastmcp_server.start(transport="http")

    assert "Server startup failed" in str(exc.value)


@pytest.mark.asyncio
async def test_stop_closes_client(fastmcp_server: NotebookLMFastMCP) -> None:
    client = AsyncMock()
    fastmcp_server.client = client

    await fastmcp_server.stop()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_handles_close_errors() -> None:
    server = NotebookLMFastMCP(ServerConfig(default_notebook_id="notebook-1"))
    client = AsyncMock()
    client.close.side_effect = RuntimeError("close failure")
    server.client = client

    await server.stop()
    client.close.assert_awaited()


def test_create_fastmcp_server(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ServerConfig(default_notebook_id="cfg")

    with patch("notebooklm_mcp.config.load_config", return_value=config) as mock_load:
        server = create_fastmcp_server("/tmp/config.json")

    mock_load.assert_called_once_with("/tmp/config.json")
    assert isinstance(server, NotebookLMFastMCP)
    assert server.config is config


@pytest.mark.asyncio
async def test_main_runs_server(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_server = SimpleNamespace(start=AsyncMock())

    monkeypatch.setattr(sys, "argv", ["server", "/tmp/config.json"])
    monkeypatch.setattr(
        server_module, "create_fastmcp_server", lambda path: fake_server
    )

    await main()

    fake_server.start.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_main_requires_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["server"])

    with pytest.raises(SystemExit) as exc:
        await main()

    assert exc.value.code == 1
    assert "Usage" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_main_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_server = SimpleNamespace(start=AsyncMock(side_effect=KeyboardInterrupt))

    monkeypatch.setattr(sys, "argv", ["server", "cfg.json"])
    monkeypatch.setattr(
        server_module, "create_fastmcp_server", lambda path: fake_server
    )

    await main()

    fake_server.start.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_main_handles_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_server = SimpleNamespace(start=AsyncMock(side_effect=RuntimeError("boom")))

    monkeypatch.setattr(sys, "argv", ["server", "cfg.json"])
    monkeypatch.setattr(
        server_module, "create_fastmcp_server", lambda path: fake_server
    )

    with pytest.raises(SystemExit) as exc:
        await main()

    assert exc.value.code == 1
