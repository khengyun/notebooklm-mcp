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

from notebooklm_mcp import client_rpc
from notebooklm_mcp.client_rpc import (
    NotebookLMRPCClient,
    _notebook_dict,
    _source_dict,
)
from notebooklm_mcp.config import AuthConfig, ServerConfig
from notebooklm_mcp.exceptions import AuthenticationError, ChatError, NavigationError


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
        source_get=None,
        fulltext=None,
        audio_list=None,
        gen_status=None,
        share_status=None,
        video_list=None,
        mind_maps=None,
        mind_map_get=None,
    ):
        self.calls: list[tuple] = []
        self._notebooks_data = list(notebooks) if notebooks is not None else []
        self._sources_data = list(sources) if sources is not None else []
        # source_id -> Source object (for sources.get), and source_id ->
        # SourceFulltext object (for sources.get_fulltext), used by copy_source.
        self._source_get = dict(source_get) if source_get else {}
        self._fulltext = dict(fulltext) if fulltext else {}
        self._audio_list = list(audio_list) if audio_list is not None else []
        self._video_list = list(video_list) if video_list is not None else []
        self._mind_maps_data = list(mind_maps) if mind_maps is not None else []
        self._mind_map_get = dict(mind_map_get) if mind_map_get else {}
        self._mind_map_tree = {"nodes": ["root"]}
        self._gen_status = gen_status or SimpleNamespace(
            task_id="task-1", status="generating", url=None, error=None
        )
        self._share_status = share_status or SimpleNamespace(
            notebook_id="nb1",
            is_public=False,
            view_level="VIEW",
            share_url=None,
            shared_users=[],
        )
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
        self.artifacts = _ArtifactsAPI(self)
        self.sharing = _SharingAPI(self)
        self.mind_maps = _MindMapsAPI(self)


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

    async def get(self, notebook_id, source_id):
        self._b.calls.append(("sources.get", notebook_id, source_id))
        return self._b._source_get.get(source_id)

    async def get_fulltext(self, notebook_id, source_id):
        self._b.calls.append(("sources.get_fulltext", notebook_id, source_id))
        return self._b._fulltext.get(source_id)


class _ChatAPI:
    def __init__(self, backend):
        self._b = backend

    async def ask(self, notebook_id, question):
        self._b.calls.append(("chat.ask", notebook_id, question))
        if self._b.ask_error is not None:
            raise self._b.ask_error
        return self._b.ask_result


class _ArtifactsAPI:
    def __init__(self, backend):
        self._b = backend

    async def generate_audio(self, notebook_id, language="en", instructions=None):
        self._b.calls.append(
            ("artifacts.generate_audio", notebook_id, language, instructions)
        )
        return self._b._gen_status

    async def list_audio(self, notebook_id):
        self._b.calls.append(("artifacts.list_audio", notebook_id))
        return list(self._b._audio_list)

    async def generate_video(self, notebook_id, language="en", instructions=None):
        self._b.calls.append(
            ("artifacts.generate_video", notebook_id, language, instructions)
        )
        return self._b._gen_status

    async def list_video(self, notebook_id):
        self._b.calls.append(("artifacts.list_video", notebook_id))
        return list(self._b._video_list)


class _MindMapsAPI:
    def __init__(self, backend):
        self._b = backend

    async def generate(self, notebook_id, source_ids=None, *, kind, language="en"):
        self._b.calls.append(
            ("mind_maps.generate", notebook_id, getattr(kind, "name", kind))
        )
        return SimpleNamespace(
            id="mm-new", notebook_id=notebook_id, title="Map", kind=kind, tree={}
        )

    async def list(self, notebook_id):
        self._b.calls.append(("mind_maps.list", notebook_id))
        return list(self._b._mind_maps_data)

    async def get_tree(self, notebook_id, mind_map_id):
        self._b.calls.append(("mind_maps.get_tree", notebook_id, mind_map_id))
        return self._b._mind_map_tree

    async def get(self, notebook_id, mind_map_id):
        self._b.calls.append(("mind_maps.get", notebook_id, mind_map_id))
        return self._b._mind_map_get.get(mind_map_id)


class _SharingAPI:
    def __init__(self, backend):
        self._b = backend

    async def get_status(self, notebook_id):
        self._b.calls.append(("sharing.get_status", notebook_id))
        return self._b._share_status

    async def set_public(self, notebook_id, public):
        self._b.calls.append(("sharing.set_public", notebook_id, public))
        self._b._share_status.is_public = public
        return self._b._share_status

    async def add_user(self, notebook_id, email, permission=None):
        self._b.calls.append(
            (
                "sharing.add_user",
                notebook_id,
                email,
                getattr(permission, "name", permission),
            )
        )
        return self._b._share_status


class _StorageCM:
    """Async context manager returned by ``from_storage(...)``.

    ``enter_error`` (when set) is raised from ``__aenter__`` to model
    notebooklm-py rejecting a missing/invalid session.
    """

    def __init__(self, backend, opened_paths, enter_error=None):
        self._backend = backend
        self._opened_paths = opened_paths
        self._enter_error = enter_error
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        if self._enter_error is not None:
            raise self._enter_error
        return self._backend

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return False


def make_backend_class(backend, opened_paths, enter_error=None):
    """Return a fake backend class whose ``from_storage`` yields ``backend``.

    ``from_storage`` accepts an optional ``path`` (the new resolver may call it
    with no argument so notebooklm-py uses its own discovery). The path actually
    passed (or ``None``) is recorded in ``opened_paths``.
    """

    class _FakeBackendClass:
        @classmethod
        def from_storage(cls, path=None):
            opened_paths.append(path)
            return _StorageCM(backend, opened_paths, enter_error=enter_error)

    return _FakeBackendClass


def install_backend(monkeypatch, backend, enter_error=None):
    """Patch ``_backend_class`` to hand out a fake class wrapping ``backend``.

    Returns the list of paths ``from_storage`` was called with, so tests can
    assert which storage_state path was used.
    """
    opened_paths: list = []
    monkeypatch.setattr(
        client_rpc,
        "_backend_class",
        lambda: make_backend_class(backend, opened_paths, enter_error=enter_error),
    )
    return opened_paths


def make_config(tmp_path, **overrides):
    """A ServerConfig whose profile_dir is an isolated tmp dir."""
    auth = AuthConfig(profile_dir=str(tmp_path / "profile"))
    cfg = ServerConfig(auth=auth, **overrides)
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
# Trivial properties
# --------------------------------------------------------------------------- #
def test_default_notebook_seeded_and_unauthenticated():
    cfg = ServerConfig(default_notebook_id="seed")
    client = NotebookLMRPCClient(cfg)
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
# _resolve_storage_state (no browser, no auth_bridge)
# --------------------------------------------------------------------------- #
def test_resolve_storage_state_explicit_existing(tmp_path):
    # An explicit storage_state_path that exists is used directly.
    explicit = tmp_path / "explicit_state.json"
    explicit.write_text("{}")
    cfg = make_config(tmp_path)
    cfg.auth.storage_state_path = str(explicit)
    client = NotebookLMRPCClient(cfg)

    assert client._resolve_storage_state() == explicit


def test_resolve_storage_state_explicit_missing_falls_through_to_default(tmp_path):
    # An explicit path that does NOT exist must be ignored; resolution then
    # falls through to the default profile_dir/storage_state.json (here present).
    cfg = make_config(tmp_path)
    cfg.auth.storage_state_path = str(tmp_path / "nope.json")
    default_file = tmp_path / "profile" / "storage_state.json"
    default_file.parent.mkdir(parents=True, exist_ok=True)
    default_file.write_text("{}")

    client = NotebookLMRPCClient(cfg)
    assert client._resolve_storage_state() == default_file


def test_resolve_storage_state_default_profile_file_exists(tmp_path):
    # No explicit path: a storage_state.json inside profile_dir is used.
    default_file = tmp_path / "profile" / "storage_state.json"
    default_file.parent.mkdir(parents=True, exist_ok=True)
    default_file.write_text("{}")

    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    assert client._resolve_storage_state() == default_file


def test_resolve_storage_state_returns_none_when_nothing_found(tmp_path):
    # No explicit path and no default file -> None, so notebooklm-py does its
    # own discovery (NOTEBOOKLM_AUTH_JSON / ~/.notebooklm).
    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    assert client._resolve_storage_state() is None


def test_start_with_no_session_uses_from_storage_no_arg(tmp_path, monkeypatch):
    # When no storage_state is found, start() must call from_storage() with NO
    # path argument (recorded as None) and still succeed against the backend.
    backend = _Backend()
    cfg = make_config(tmp_path)  # profile dir has no storage_state.json
    client = NotebookLMRPCClient(cfg)
    opened = install_backend(monkeypatch, backend)

    asyncio.run(client.start())
    assert opened == [None]
    assert client._backend is backend


def test_start_raises_authentication_error_when_no_session(tmp_path, monkeypatch):
    # If entering the backend context fails (no session anywhere), start() must
    # surface a clear AuthenticationError and reset its context manager.
    backend = _Backend()
    cfg = make_config(tmp_path)
    client = NotebookLMRPCClient(cfg)
    install_backend(monkeypatch, backend, enter_error=RuntimeError("no auth json"))

    with pytest.raises(AuthenticationError, match="notebooklm login"):
        asyncio.run(client.start())
    # Failed enter must leave the client cleanly un-started.
    assert client._backend is None
    assert client._cm is None


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


# --------------------------------------------------------------------------- #
# Compose: copy_source / create_notebook_from_sources
# --------------------------------------------------------------------------- #
def test_copy_source_with_url_readds_by_url(monkeypatch, tmp_path):
    # A source carrying a URL is copied via sources.add_url (no fulltext needed).
    src = SimpleNamespace(id="s1", title="Doc", url="https://example.com/p.pdf")
    backend = _Backend(source_get={"s1": src})
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.copy_source("nbA", "s1", "nbB"))

    assert ("sources.get", "nbA", "s1") in backend.calls
    assert ("sources.add_url", "nbB", "https://example.com/p.pdf") in backend.calls
    # Must NOT fall back to fulltext when a URL is present.
    assert not any(c[0] == "sources.get_fulltext" for c in backend.calls)
    assert result["id"] == "src-url"


def test_copy_source_without_url_readds_text_from_fulltext(monkeypatch, tmp_path):
    # A URL-less source is copied by re-adding its extracted full-text content.
    src = SimpleNamespace(id="s2", title="Note", url=None)
    full = SimpleNamespace(title="Note", content="the body text")
    backend = _Backend(source_get={"s2": src}, fulltext={"s2": full})
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.copy_source("nbA", "s2", "nbB"))

    assert ("sources.get_fulltext", "nbA", "s2") in backend.calls
    assert ("sources.add_text", "nbB", "Note", "the body text") in backend.calls
    assert result["id"] == "src-text"


def test_copy_source_missing_source_raises(monkeypatch, tmp_path):
    backend = _Backend(source_get={})  # sources.get returns None
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    with pytest.raises(NavigationError, match="not found"):
        asyncio.run(client.copy_source("nbA", "missing", "nbB"))


def test_create_notebook_from_sources_copies_all(monkeypatch, tmp_path):
    s1 = SimpleNamespace(id="s1", title="A", url="https://a.com")
    s2 = SimpleNamespace(id="s2", title="B", url="https://b.com")
    backend = _Backend(source_get={"s1": s1, "s2": s2})
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(
        client.create_notebook_from_sources(
            "Merged",
            [
                {"notebook_id": "nb1", "source_id": "s1"},
                {"notebook_id": "nb2", "source_id": "s2"},
            ],
        )
    )

    # A new notebook was created and both sources copied into it (nb-new).
    assert ("notebooks.create", "Merged") in backend.calls
    assert ("sources.add_url", "nb-new", "https://a.com") in backend.calls
    assert ("sources.add_url", "nb-new", "https://b.com") in backend.calls
    assert result["notebook"]["id"] == "nb-new"
    assert len(result["copied"]) == 2
    assert result["failed"] == []


def test_create_notebook_from_sources_reports_partial_failure(monkeypatch, tmp_path):
    # One good source, one missing: the merge must continue and report the bad
    # one in `failed` rather than aborting.
    s1 = SimpleNamespace(id="s1", title="A", url="https://a.com")
    backend = _Backend(source_get={"s1": s1})  # "bad" not present -> raises
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(
        client.create_notebook_from_sources(
            "Merged",
            [
                {"notebook_id": "nb1", "source_id": "s1"},
                {"notebook_id": "nb1", "source_id": "bad"},
            ],
        )
    )

    assert len(result["copied"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["source_id"] == "bad"
    assert "error" in result["failed"][0]


# --------------------------------------------------------------------------- #
# Audio Overview
# --------------------------------------------------------------------------- #
def test_generate_audio_overview(monkeypatch, tmp_path):
    backend = _Backend(
        gen_status=SimpleNamespace(
            task_id="t-9", status="generating", url=None, error=None
        )
    )
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(
        client.generate_audio_overview("nb1", instructions="be brief", language="vi")
    )

    assert ("artifacts.generate_audio", "nb1", "vi", "be brief") in backend.calls
    assert result["task_id"] == "t-9"
    assert result["status"] == "generating"


def test_list_audio_overviews(monkeypatch, tmp_path):
    art = SimpleNamespace(
        id="a1", title="Deep Dive", status="ready", url="https://x/a1"
    )
    backend = _Backend(audio_list=[art])
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    audios = asyncio.run(client.list_audio_overviews("nb1"))

    assert ("artifacts.list_audio", "nb1") in backend.calls
    assert audios == [
        {"id": "a1", "title": "Deep Dive", "status": "ready", "url": "https://x/a1"}
    ]


# --------------------------------------------------------------------------- #
# Sharing
# --------------------------------------------------------------------------- #
def test_get_share_status_is_read_only(monkeypatch, tmp_path):
    status = SimpleNamespace(
        notebook_id="nb1",
        is_public=True,
        view_level="VIEW",
        share_url="https://share/nb1",
        shared_users=[],
    )
    backend = _Backend(share_status=status)
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.get_share_status("nb1"))

    assert backend.calls[-1] == ("sharing.get_status", "nb1")
    # Read-only: it must NOT call set_public/add_user.
    assert not any(
        c[0] in ("sharing.set_public", "sharing.add_user") for c in backend.calls
    )
    assert result["is_public"] is True
    assert result["share_url"] == "https://share/nb1"


def test_set_notebook_public(monkeypatch, tmp_path):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.set_notebook_public("nb1", True))

    assert ("sharing.set_public", "nb1", True) in backend.calls
    assert result["is_public"] is True


def test_share_notebook_with_user_maps_permission(monkeypatch, tmp_path):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    asyncio.run(client.share_notebook_with_user("nb1", "a@b.com", permission="editor"))

    # The string permission is mapped to the SharePermission enum (EDITOR).
    call = [c for c in backend.calls if c[0] == "sharing.add_user"][0]
    assert call[1] == "nb1"
    assert call[2] == "a@b.com"
    assert call[3] == "EDITOR"


def test_share_notebook_unknown_permission_falls_back_to_viewer(monkeypatch, tmp_path):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    asyncio.run(client.share_notebook_with_user("nb1", "a@b.com", permission="bogus"))

    call = [c for c in backend.calls if c[0] == "sharing.add_user"][0]
    assert call[3] == "VIEWER"


# --------------------------------------------------------------------------- #
# Video Overview
# --------------------------------------------------------------------------- #
def test_generate_video_overview(monkeypatch, tmp_path):
    backend = _Backend(
        gen_status=SimpleNamespace(
            task_id="v-1", status="in_progress", url=None, error=None
        )
    )
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.generate_video_overview("nb1", language="vi"))

    assert ("artifacts.generate_video", "nb1", "vi", None) in backend.calls
    assert result["task_id"] == "v-1"
    assert result["status"] == "in_progress"


def test_list_video_overviews(monkeypatch, tmp_path):
    art = SimpleNamespace(
        id="v9", title="Explainer", status="ready", url="https://x/v9"
    )
    backend = _Backend(video_list=[art])
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    videos = asyncio.run(client.list_video_overviews("nb1"))

    assert ("artifacts.list_video", "nb1") in backend.calls
    assert videos == [
        {"id": "v9", "title": "Explainer", "status": "ready", "url": "https://x/v9"}
    ]


# --------------------------------------------------------------------------- #
# Mind Map
# --------------------------------------------------------------------------- #
def test_generate_mind_map_maps_kind(monkeypatch, tmp_path):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.generate_mind_map("nb1", kind="note_backed"))

    # The string kind is mapped to the MindMapKind enum (NOTE_BACKED).
    assert ("mind_maps.generate", "nb1", "NOTE_BACKED") in backend.calls
    assert result["id"] == "mm-new"
    # A bare dict (no tree) is returned for generate.
    assert "tree" not in result


def test_generate_mind_map_unknown_kind_falls_back_interactive(monkeypatch, tmp_path):
    backend = _Backend()
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    asyncio.run(client.generate_mind_map("nb1", kind="bogus"))

    call = [c for c in backend.calls if c[0] == "mind_maps.generate"][0]
    assert call[2] == "INTERACTIVE"


def test_list_mind_maps(monkeypatch, tmp_path):
    mm = SimpleNamespace(id="mm1", notebook_id="nb1", title="M", kind="INTERACTIVE")
    backend = _Backend(mind_maps=[mm])
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    maps = asyncio.run(client.list_mind_maps("nb1"))

    assert ("mind_maps.list", "nb1") in backend.calls
    assert maps == [
        {"id": "mm1", "title": "M", "kind": "INTERACTIVE", "notebook_id": "nb1"}
    ]


def test_get_mind_map_includes_tree(monkeypatch, tmp_path):
    mm = SimpleNamespace(
        id="mm1", notebook_id="nb1", title="M", kind="INTERACTIVE", tree={"root": []}
    )
    backend = _Backend(mind_map_get={"mm1": mm})
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.get_mind_map("nb1", "mm1"))

    assert ("mind_maps.get", "nb1", "mm1") in backend.calls
    assert result["tree"] == {"root": []}


def test_get_mind_map_missing_raises(monkeypatch, tmp_path):
    backend = _Backend(mind_map_get={})  # get returns None
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))
    with pytest.raises(NavigationError, match="not found"):
        asyncio.run(client.get_mind_map("nb1", "missing"))


def test_get_mind_map_fetches_tree_when_absent(monkeypatch, tmp_path):
    # When the map object has no inline tree, the client fetches it via get_tree.
    mm = SimpleNamespace(
        id="mm1", notebook_id="nb1", title="M", kind="INTERACTIVE", tree=None
    )
    backend = _Backend(mind_map_get={"mm1": mm})
    client = asyncio.run(started_client(monkeypatch, tmp_path, backend))

    result = asyncio.run(client.get_mind_map("nb1", "mm1"))

    assert ("mind_maps.get_tree", "nb1", "mm1") in backend.calls
    assert result["tree"] == {"nodes": ["root"]}
