"""Deterministic tests for the RPC engine (:mod:`notebooklm_mcp.client_rpc`).

The RPC client wraps ``notebooklm-py`` via the module-level
``_backend_class()`` indirection. These tests **never import real
notebooklm-py and never touch a browser/network**: we monkeypatch
``client_rpc._backend_class`` to return a *faithful* fake backend whose async
surface mirrors the real one (``from_storage`` async context manager exposing
``notebooks`` / ``sources`` / ``chat`` sub-APIs). The production client logic
(``start``/``authenticate``/``send_message``/management methods) runs unchanged
against the fake -- so a mutation in the real client logic is caught here.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from notebooklm_mcp import auth_bridge, client_rpc
from notebooklm_mcp.client_rpc import (
    NotebookLMRPCClient,
    _notebook_dict,
    _source_dict,
)
from notebooklm_mcp.config import AuthConfig, ServerConfig
from notebooklm_mcp.exceptions import ChatError, NavigationError


# --------------------------------------------------------------------------- #
# Faithful fake notebooklm-py backend.
#
# The real backend is opened via ``NotebookLMClient.from_storage(path=...)``,
# which is an async context manager. Its ``__aenter__`` yields an object with
# ``.notebooks`` / ``.sources`` / ``.chat`` sub-APIs whose methods are all
# coroutines. The fakes below model exactly that shape and record every call so
# tests can assert the client forwards the right method + args. Backend data
# lives in private attrs; the public ``.notebooks`` / ``.sources`` / ``.chat``
# names are the sub-API objects (matching the real surface the client uses).
# --------------------------------------------------------------------------- #
class _Backend:
    """Faithful fake backend: data in private attrs, sub-APIs public."""

    def __init__(
        self,
        *,
        notebooks=None,
        sources=None,
        summary="A summary",
        ask_result=None,
        list_error=None,
        ask_error=None,
    ):
        self.calls: list[tuple] = []
        self._notebooks_data = list(notebooks) if notebooks is not None else []
        self._sources_data = list(sources) if sources is not None else []
        self.summary = summary
        self.ask_result = (
            ask_result
            if ask_result is not None
            else SimpleNamespace(answer="default-answer")
        )
        self.list_error = list_error
        self.ask_error = ask_error
        self.notebooks = _NotebooksAPI(self)
        self.sources = _SourcesAPI(self)
        self.chat = _ChatAPI(self)


class _NotebooksAPI:
    def __init__(self, backend):
        self._b = backend

    async def list(self):
        self._b.calls.append(("notebooks.list",))
        if self._b.list_error is not None:
            raise self._b.list_error
        return list(self._b._notebooks_data)

    async def create(self, title):
        self._b.calls.append(("notebooks.create", title))
        return SimpleNamespace(id="nb-new", title=title, emoji="✨", source_count=0)

    async def rename(self, notebook_id, new_title):
        self._b.calls.append(("notebooks.rename", notebook_id, new_title))
        return SimpleNamespace(
            id=notebook_id, title=new_title, emoji="📓", source_count=2
        )

    async def delete(self, notebook_id):
        self._b.calls.append(("notebooks.delete", notebook_id))
        return None

    async def get_summary(self, notebook_id):
        self._b.calls.append(("notebooks.get_summary", notebook_id))
        return self._b.summary


class _SourcesAPI:
    def __init__(self, backend):
        self._b = backend

    async def list(self, notebook_id):
        self._b.calls.append(("sources.list", notebook_id))
        return list(self._b._sources_data)

    async def add_url(self, notebook_id, url):
        self._b.calls.append(("sources.add_url", notebook_id, url))
        return SimpleNamespace(id="src-url", title=url, type="url", status="processing")

    async def add_text(self, notebook_id, title, text):
        self._b.calls.append(("sources.add_text", notebook_id, title, text))
        return SimpleNamespace(id="src-text", title=title, type="text", status="ready")

    async def delete(self, notebook_id, source_id):
        self._b.calls.append(("sources.delete", notebook_id, source_id))
        return None


class _ChatAPI:
    def __init__(self, backend):
        self._b = backend

    async def ask(self, notebook_id, question):
        self._b.calls.append(("chat.ask", notebook_id, question))
        if self._b.ask_error is not None:
            raise self._b.ask_error
        return self._b.ask_result


class _StorageCM:
    """Async context manager returned by ``from_storage(path=...)``."""

    def __init__(self, backend, opened_paths):
        self._backend = backend
        self._opened_paths = opened_paths
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self._backend

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return False


def make_backend_class(backend, opened_paths):
    """Return a fake backend class whose ``from_storage`` yields ``backend``."""

    class _FakeBackendClass:
        @classmethod
        def from_storage(cls, path):
            opened_paths.append(path)
            return _StorageCM(backend, opened_paths)

    return _FakeBackendClass


def install_backend(monkeypatch, backend):
    """Patch ``_backend_class`` to hand out a fake class wrapping ``backend``.

    Returns the list of paths ``from_storage`` was called with, so tests can
    assert which storage_state path was used.
    """
    opened_paths: list = []
    monkeypatch.setattr(
        client_rpc,
        "_backend_class",
        lambda: make_backend_class(backend, opened_paths),
    )
    return opened_paths


def make_config(tmp_path, **overrides):
    """A ServerConfig whose profile_dir is an isolated tmp dir."""
    auth = AuthConfig(profile_dir=str(tmp_path / "profile"))
    cfg = ServerConfig(auth=auth, engine="rpc", **overrides)
    return cfg


async def started_client(monkeypatch, tmp_path, backend, *, storage_file=None):
    """Build + start an RPC client against ``backend``.

    A real ``storage_state`` file is created so ``_resolve_storage_state``
    returns it directly (no bootstrap, no browser).
    """
    if storage_file is None:
        storage_file = tmp_path / "profile" / "storage_state.json"
        storage_file.parent.mkdir(parents=True, exist_ok=True)
        storage_file.write_text("{}")
    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    install_backend(monkeypatch, backend)
    await client.start()
    return client


# --------------------------------------------------------------------------- #
# Pure mapping helpers
# --------------------------------------------------------------------------- #
def test_notebook_dict_serializes_all_fields():
    nb = SimpleNamespace(id="n1", title="T", emoji="📘", source_count=5)
    assert _notebook_dict(nb) == {
        "id": "n1",
        "title": "T",
        "emoji": "📘",
        "source_count": 5,
    }


def test_notebook_dict_tolerates_missing_attrs():
    # An object missing every attribute must map every field to None (not crash
    # and not invent values).
    assert _notebook_dict(object()) == {
        "id": None,
        "title": None,
        "emoji": None,
        "source_count": None,
    }


def test_source_dict_serializes_and_prefers_type():
    src = SimpleNamespace(id="s1", title="Doc", type="pdf", status="ready")
    assert _source_dict(src) == {
        "id": "s1",
        "title": "Doc",
        "type": "pdf",
        "status": "ready",
    }


def test_source_dict_falls_back_to_source_type():
    # When ``type`` is absent the mapper must fall back to ``source_type``.
    src = SimpleNamespace(id="s2", title="Doc", source_type="website", status="ok")
    assert _source_dict(src)["type"] == "website"


def test_source_dict_tolerates_missing_attrs():
    assert _source_dict(object()) == {
        "id": None,
        "title": None,
        "type": None,
        "status": None,
    }


# --------------------------------------------------------------------------- #
# Engine flags / trivial properties
# --------------------------------------------------------------------------- #
def test_supports_management_is_true():
    assert NotebookLMRPCClient.supports_management is True


def test_driver_is_none_and_default_notebook_seeded():
    cfg = ServerConfig(engine="rpc", default_notebook_id="seed")
    client = NotebookLMRPCClient(cfg)
    assert client.driver is None
    assert client.current_notebook_id == "seed"
    assert client.is_authenticated is False


# --------------------------------------------------------------------------- #
# start() lifecycle + idempotency
# --------------------------------------------------------------------------- #
def test_start_enters_context_and_stores_backend(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    # The backend the client holds is exactly the one yielded by __aenter__.
    assert client._backend is backend
    assert client._cm is not None and client._cm.entered is True


def test_start_is_idempotent(tmp_path, monkeypatch):
    backend = _Backend()
    storage_file = tmp_path / "profile" / "storage_state.json"
    storage_file.parent.mkdir(parents=True, exist_ok=True)
    storage_file.write_text("{}")
    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    opened = install_backend(monkeypatch, backend)

    asyncio.run(client.start())
    first_backend = client._backend
    asyncio.run(client.start())
    # Second start is a no-op: backend unchanged, from_storage called once.
    assert client._backend is first_backend
    assert len(opened) == 1


# --------------------------------------------------------------------------- #
# _resolve_storage_state
# --------------------------------------------------------------------------- #
def test_resolve_storage_state_explicit_existing(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit_state.json"
    explicit.write_text("{}")
    cfg = make_config(tmp_path)
    cfg.auth.storage_state_path = str(explicit)
    client = NotebookLMRPCClient(cfg)

    resolved = asyncio.run(client._resolve_storage_state())
    assert resolved == explicit


def test_resolve_storage_state_explicit_missing_falls_through(tmp_path, monkeypatch):
    # Explicit path that does NOT exist must be ignored; resolution then falls
    # through to the default-path branch (which here exists).
    missing = tmp_path / "nope.json"
    cfg = make_config(tmp_path)
    cfg.auth.storage_state_path = str(missing)
    # Make the default path exist so we land on the default branch, not bootstrap.
    default_file = tmp_path / "default_state.json"
    default_file.write_text("{}")
    # _resolve_storage_state does `from .auth_bridge import default_storage_state_path`
    # at call time, so patching the source module symbol is what takes effect.
    monkeypatch.setattr(
        auth_bridge, "default_storage_state_path", lambda _cfg: default_file
    )

    client = NotebookLMRPCClient(cfg)
    resolved = asyncio.run(client._resolve_storage_state())
    assert resolved == default_file


def test_resolve_storage_state_default_path_exists(tmp_path, monkeypatch):
    default_file = tmp_path / "default_state.json"
    default_file.write_text("{}")
    monkeypatch.setattr(
        auth_bridge, "default_storage_state_path", lambda _cfg: default_file
    )

    async def _should_not_run(*_a, **_k):  # pragma: no cover - must NOT be called
        raise AssertionError("export_storage_state must not run when default exists")

    monkeypatch.setattr(auth_bridge, "export_storage_state", _should_not_run)

    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    resolved = asyncio.run(client._resolve_storage_state())
    assert resolved == default_file


def test_resolve_storage_state_bootstraps_when_missing(tmp_path, monkeypatch):
    # No explicit path, default path does NOT exist -> must call
    # export_storage_state (the one-time bootstrap) and return its result.
    target = tmp_path / "profile" / "storage_state.json"
    bootstrapped = tmp_path / "bootstrapped.json"
    bootstrapped.write_text("{}")
    monkeypatch.setattr(auth_bridge, "default_storage_state_path", lambda _cfg: target)

    export_calls = []

    async def fake_export(config, out_path):
        export_calls.append((config, out_path))
        return bootstrapped

    monkeypatch.setattr(auth_bridge, "export_storage_state", fake_export)

    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    resolved = asyncio.run(client._resolve_storage_state())

    assert resolved == bootstrapped
    # export was called once, with the config and the default target path.
    assert len(export_calls) == 1
    assert export_calls[0][0] is cfg
    assert export_calls[0][1] == target


# --------------------------------------------------------------------------- #
# authenticate()
# --------------------------------------------------------------------------- #
def test_authenticate_success(tmp_path, monkeypatch):
    backend = _Backend(notebooks=[SimpleNamespace(id="n", title="t")])
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.authenticate())
    assert result is True
    assert client.is_authenticated is True
    # The cheap auth probe is a notebooks.list call.
    assert ("notebooks.list",) in backend.calls


def test_authenticate_failure_when_list_raises(tmp_path, monkeypatch):
    backend = _Backend(list_error=RuntimeError("401 unauthorized"))
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.authenticate())
    assert result is False
    assert client.is_authenticated is False


def test_authenticate_without_backend_raises(tmp_path):
    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    # Never started -> _require_backend raises ChatError.
    with pytest.raises(ChatError, match="not started"):
        asyncio.run(client.authenticate())


# --------------------------------------------------------------------------- #
# Chat surface
# --------------------------------------------------------------------------- #
def test_send_message_stores_answer_and_get_response_returns_it(tmp_path, monkeypatch):
    backend = _Backend(ask_result=SimpleNamespace(answer="forty-two"))
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    client.current_notebook_id = "nb1"

    asyncio.run(client.send_message("What is the meaning?"))
    # chat.ask was called with the current notebook id + message.
    assert ("chat.ask", "nb1", "What is the meaning?") in backend.calls
    # The stored answer is exactly the backend's .answer (mutation: dropping the
    # store leaves the fallback string and fails this assertion).
    assert asyncio.run(client.get_response()) == "forty-two"


def test_get_response_empty_falls_back(tmp_path, monkeypatch):
    backend = _Backend(ask_result=SimpleNamespace(answer=""))
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    client.current_notebook_id = "nb1"

    asyncio.run(client.send_message("q"))
    assert asyncio.run(client.get_response()) == "No response content found"


def test_get_response_before_any_send_is_fallback(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    # No send_message yet -> empty stored answer -> fallback.
    assert asyncio.run(client.get_response()) == "No response content found"


def test_send_message_without_notebook_raises(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    client.current_notebook_id = None

    with pytest.raises(NavigationError, match="No notebook selected"):
        asyncio.run(client.send_message("hi"))
    # The chat backend was never asked because the notebook guard fired first.
    assert not any(c[0] == "chat.ask" for c in backend.calls)


def test_send_message_wraps_backend_error_as_chat_error(tmp_path, monkeypatch):
    backend = _Backend(ask_error=RuntimeError("rpc 500"))
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    client.current_notebook_id = "nb1"

    with pytest.raises(ChatError, match="RPC chat failed"):
        asyncio.run(client.send_message("hi"))


def test_navigate_to_notebook_sets_current(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    returned = asyncio.run(client.navigate_to_notebook("nb-xyz"))
    assert returned == "nb-xyz"
    assert client.current_notebook_id == "nb-xyz"


# --------------------------------------------------------------------------- #
# Notebook management
# --------------------------------------------------------------------------- #
def test_list_notebooks_maps_each(tmp_path, monkeypatch):
    backend = _Backend(
        notebooks=[
            SimpleNamespace(id="a", title="Alpha", emoji="🅰", source_count=1),
            SimpleNamespace(id="b", title="Beta", emoji="🅱", source_count=3),
        ]
    )
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.list_notebooks())
    assert result == [
        {"id": "a", "title": "Alpha", "emoji": "🅰", "source_count": 1},
        {"id": "b", "title": "Beta", "emoji": "🅱", "source_count": 3},
    ]


def test_create_notebook_forwards_title_and_maps(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.create_notebook("My Notebook"))
    assert ("notebooks.create", "My Notebook") in backend.calls
    assert result == {
        "id": "nb-new",
        "title": "My Notebook",
        "emoji": "✨",
        "source_count": 0,
    }


def test_rename_notebook_forwards_args_and_maps(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.rename_notebook("nb1", "New Name"))
    assert ("notebooks.rename", "nb1", "New Name") in backend.calls
    assert result["id"] == "nb1"
    assert result["title"] == "New Name"


def test_delete_notebook_forwards_id(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    assert asyncio.run(client.delete_notebook("nb-del")) is None
    assert ("notebooks.delete", "nb-del") in backend.calls


def test_get_notebook_summary_coerces_to_str(tmp_path, monkeypatch):
    backend = _Backend(summary=12345)  # non-string to prove str() coercion
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.get_notebook_summary("nb1"))
    assert ("notebooks.get_summary", "nb1") in backend.calls
    assert result == "12345"
    assert isinstance(result, str)


# --------------------------------------------------------------------------- #
# Source management
# --------------------------------------------------------------------------- #
def test_list_sources_forwards_id_and_maps(tmp_path, monkeypatch):
    backend = _Backend(
        sources=[
            SimpleNamespace(id="s1", title="Src1", type="pdf", status="ready"),
            SimpleNamespace(id="s2", title="Src2", source_type="url", status="busy"),
        ]
    )
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.list_sources("nb1"))
    assert ("sources.list", "nb1") in backend.calls
    assert result[0] == {
        "id": "s1",
        "title": "Src1",
        "type": "pdf",
        "status": "ready",
    }
    # Second source has no ``type`` -> mapper falls back to source_type.
    assert result[1]["type"] == "url"


def test_add_source_url_forwards_and_maps(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.add_source_url("nb1", "https://example.com"))
    assert ("sources.add_url", "nb1", "https://example.com") in backend.calls
    assert result == {
        "id": "src-url",
        "title": "https://example.com",
        "type": "url",
        "status": "processing",
    }


def test_add_source_text_forwards_and_maps(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.add_source_text("nb1", "Title", "body text"))
    assert ("sources.add_text", "nb1", "Title", "body text") in backend.calls
    assert result["id"] == "src-text"
    assert result["title"] == "Title"
    assert result["type"] == "text"


def test_delete_source_forwards_ids(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    assert asyncio.run(client.delete_source("nb1", "src9")) is None
    assert ("sources.delete", "nb1", "src9") in backend.calls


# --------------------------------------------------------------------------- #
# Management methods all require a started backend
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.list_notebooks(),
        lambda c: c.create_notebook("t"),
        lambda c: c.rename_notebook("n", "t"),
        lambda c: c.delete_notebook("n"),
        lambda c: c.get_notebook_summary("n"),
        lambda c: c.list_sources("n"),
        lambda c: c.add_source_url("n", "u"),
        lambda c: c.add_source_text("n", "t", "x"),
        lambda c: c.delete_source("n", "s"),
    ],
)
def test_management_methods_require_started_backend(tmp_path, call):
    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    with pytest.raises(ChatError, match="not started"):
        asyncio.run(call(client))


# --------------------------------------------------------------------------- #
# close()
# --------------------------------------------------------------------------- #
def test_close_resets_state_and_calls_aexit(tmp_path, monkeypatch):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    client._is_authenticated = True
    cm = client._cm

    asyncio.run(client.close())
    assert cm.exited is True
    assert client._backend is None
    assert client._cm is None
    assert client.is_authenticated is False


def test_close_is_idempotent_without_backend(tmp_path):
    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    # Never started -> close must be safe and a no-op.
    asyncio.run(client.close())
    asyncio.run(client.close())
    assert client._backend is None
    assert client._cm is None
