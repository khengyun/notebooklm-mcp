"""RPC engine: a NotebookLM client backed by ``notebooklm-py`` (batchexecute).

This is the primary engine. It speaks NotebookLM's internal RPC API instead of
driving the DOM, which makes it fast and — crucially — gives full **notebook
and source management** (list/create/delete/rename notebooks, add/delete
sources) that the browser engine cannot do.

It implements the same lifecycle/chat surface as
:class:`notebooklm_mcp.client.NotebookLMClient` (``start``/``authenticate``/
``send_message``/``get_response``/``navigate_to_notebook``/``close``) so the
MCP server and CLI use it interchangeably, and adds management methods on top.

Auth: the browser profile is used only to bootstrap a Playwright
``storage_state`` (see :mod:`notebooklm_mcp.auth_bridge`); all actions go
through the RPC backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .config import ServerConfig
from .exceptions import ChatError, NavigationError


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

    # The RPC engine has no browser page; ``driver`` stays None so the legacy
    # health check reports "not_started" rather than crashing.
    @property
    def driver(self) -> None:
        return None

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """Open the RPC backend using a bootstrapped storage_state. Idempotent."""
        if self._backend is not None:
            return
        storage = await self._resolve_storage_state()
        backend_cls = _backend_class()
        self._cm = backend_cls.from_storage(path=str(storage))
        self._backend = await self._cm.__aenter__()
        logger.info("RPC engine (notebooklm-py) started")

    async def _resolve_storage_state(self) -> Path:
        explicit = self.config.auth.storage_state_path
        if explicit:
            p = Path(explicit).expanduser()
            if p.exists():
                return p
        from .auth_bridge import default_storage_state_path, export_storage_state

        target = default_storage_state_path(self.config)
        if target.exists():
            return target
        # Bootstrap from the persistent browser profile (one-time login reuse).
        return await export_storage_state(self.config, target)

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
