"""RPC engine: a NotebookLM client backed by ``notebooklm-py`` (batchexecute).

This is the only engine. It speaks NotebookLM's internal RPC API instead of
driving the DOM, which makes it fast and — crucially — gives full **notebook
and source management** (list/create/delete/rename notebooks, add/delete
sources).

It exposes the lifecycle/chat surface (``start``/``authenticate``/
``send_message``/``get_response``/``navigate_to_notebook``/``close``) used by
the MCP server and CLI, and adds management methods on top.

Auth: notebooklm-py owns the session. A ``storage_state`` JSON (created with
``notebooklm login``) is discovered from config (``auth.storage_state_path`` or
a ``storage_state.json`` in the profile dir) or from notebooklm-py's own
defaults (``NOTEBOOKLM_AUTH_JSON`` env / ``~/.notebooklm/storage_state.json``).
This module never launches a browser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .config import ServerConfig
from .exceptions import AuthenticationError, ChatError, NavigationError


def _backend_class() -> Any:
    """Return the notebooklm-py client class (lazy import; monkeypatchable)."""
    from notebooklm.client import NotebookLMClient as _RPCBackend

    return _RPCBackend


def _notebook_dict(nb: Any) -> Dict[str, Any]:
    return {
        "id": getattr(nb, "id", None),
        "title": getattr(nb, "title", None),
        "emoji": getattr(nb, "emoji", None),
        "source_count": getattr(nb, "source_count", None),
    }


def _source_dict(src: Any) -> Dict[str, Any]:
    return {
        "id": getattr(src, "id", None),
        "title": getattr(src, "title", None),
        "type": getattr(src, "type", None) or getattr(src, "source_type", None),
        "status": getattr(src, "status", None),
    }


class NotebookLMRPCClient:
    """High-level RPC client (notebooklm-py backend) with management support."""

    #: Marks this engine as capable of notebook/source management so the server
    #: can expose those tools (the browser engine sets this False).
    supports_management = True

    def __init__(self, config: ServerConfig):
        self.config = config
        self.current_notebook_id: Optional[str] = config.default_notebook_id
        self._is_authenticated = False
        self._backend: Optional[Any] = None
        self._cm: Optional[Any] = None
        self._last_answer = ""

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """Open the RPC backend from a notebooklm-py session. Idempotent.

        The session is resolved (no browser) and handed to
        ``backend.from_storage``. If no session exists anywhere, entering the
        backend context raises and we surface a clear ``AuthenticationError``
        telling the user to run ``notebooklm login``.
        """
        if self._backend is not None:
            return
        storage = self._resolve_storage_state()
        backend_cls = _backend_class()
        if storage is not None:
            self._cm = backend_cls.from_storage(path=str(storage))
        else:
            # No path: notebooklm-py discovers NOTEBOOKLM_AUTH_JSON or
            # ~/.notebooklm/storage_state.json on its own.
            self._cm = backend_cls.from_storage()
        try:
            self._backend = await self._cm.__aenter__()
        except Exception as exc:
            self._cm = None
            raise AuthenticationError(
                "No NotebookLM session found. Run `notebooklm login` or set "
                "auth.storage_state_path."
            ) from exc
        logger.info("RPC engine (notebooklm-py) started")

    def _resolve_storage_state(self) -> Optional[Path]:
        """Locate a storage_state file, or ``None`` to defer to notebooklm-py.

        Order: explicit ``auth.storage_state_path`` (if it exists), then a
        ``storage_state.json`` in ``auth.profile_dir`` (if it exists), else
        ``None`` so notebooklm-py uses its own discovery.
        """
        explicit = self.config.auth.storage_state_path
        if explicit:
            p = Path(explicit).expanduser()
            if p.exists():
                return p
        default = Path(self.config.auth.profile_dir).expanduser() / "storage_state.json"
        if default.exists():
            return default
        return None

    async def authenticate(self) -> bool:
        """Verify the session by issuing a cheap RPC (list notebooks)."""
        backend = self._require_backend()
        try:
            await backend.notebooks.list()
            self._is_authenticated = True
        except Exception as exc:  # noqa: BLE001 - any failure means not authed
            logger.warning(f"RPC auth check failed: {exc}")
            self._is_authenticated = False
        return self._is_authenticated

    async def close(self) -> None:
        """Close the RPC backend. Idempotent."""
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception as exc:  # pragma: no cover - best-effort cleanup
                logger.debug(f"RPC close failed: {exc}")
        self._cm = None
        self._backend = None
        self._is_authenticated = False

    # ------------------------------------------------------------------ #
    # Chat (compatible with the browser engine surface)
    # ------------------------------------------------------------------ #
    async def send_message(self, message: str) -> None:
        backend = self._require_backend()
        notebook_id = self._require_notebook()
        try:
            result = await backend.chat.ask(notebook_id, message)
        except Exception as exc:  # noqa: BLE001
            raise ChatError(f"RPC chat failed: {exc}") from exc
        self._last_answer = getattr(result, "answer", str(result))

    async def get_response(
        self, wait_for_completion: bool = True, max_wait: Optional[int] = None
    ) -> str:
        # ``chat.ask`` already returns the completed answer, so the stored
        # answer is final; the wait args are accepted for interface parity.
        return self._last_answer or "No response content found"

    async def navigate_to_notebook(self, notebook_id: str) -> str:
        self.current_notebook_id = notebook_id
        return notebook_id

    # ------------------------------------------------------------------ #
    # Notebook management
    # ------------------------------------------------------------------ #
    async def list_notebooks(self) -> List[Dict[str, Any]]:
        backend = self._require_backend()
        return [_notebook_dict(nb) for nb in await backend.notebooks.list()]

    async def create_notebook(self, title: str) -> Dict[str, Any]:
        backend = self._require_backend()
        return _notebook_dict(await backend.notebooks.create(title))

    async def rename_notebook(self, notebook_id: str, new_title: str) -> Dict[str, Any]:
        backend = self._require_backend()
        return _notebook_dict(await backend.notebooks.rename(notebook_id, new_title))

    async def delete_notebook(self, notebook_id: str) -> None:
        backend = self._require_backend()
        await backend.notebooks.delete(notebook_id)

    async def get_notebook_summary(self, notebook_id: str) -> str:
        backend = self._require_backend()
        return str(await backend.notebooks.get_summary(notebook_id))

    # ------------------------------------------------------------------ #
    # Source management
    # ------------------------------------------------------------------ #
    async def list_sources(self, notebook_id: str) -> List[Dict[str, Any]]:
        backend = self._require_backend()
        return [_source_dict(s) for s in await backend.sources.list(notebook_id)]

    async def add_source_url(self, notebook_id: str, url: str) -> Dict[str, Any]:
        backend = self._require_backend()
        return _source_dict(await backend.sources.add_url(notebook_id, url))

    async def add_source_text(
        self, notebook_id: str, title: str, text: str
    ) -> Dict[str, Any]:
        backend = self._require_backend()
        return _source_dict(await backend.sources.add_text(notebook_id, title, text))

    async def delete_source(self, notebook_id: str, source_id: str) -> None:
        backend = self._require_backend()
        await backend.sources.delete(notebook_id, source_id)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _require_backend(self) -> Any:
        if self._backend is None:
            raise ChatError("RPC engine not started")
        return self._backend

    def _require_notebook(self) -> str:
        if not self.current_notebook_id:
            raise NavigationError("No notebook selected")
        return self.current_notebook_id
