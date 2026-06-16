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


def _jsonable(value: Any) -> Any:
    """Coerce backend objects/enums into JSON-serializable values."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return str(value)


def _artifact_dict(art: Any) -> Dict[str, Any]:
    return {
        "id": getattr(art, "id", None),
        "title": getattr(art, "title", None),
        "status": _jsonable(getattr(art, "status", None)),
        "url": getattr(art, "url", None),
    }


def _gen_status_dict(s: Any) -> Dict[str, Any]:
    return {
        "task_id": getattr(s, "task_id", None),
        "status": _jsonable(getattr(s, "status", None)),
        "url": getattr(s, "url", None),
        "error": getattr(s, "error", None),
    }


def _share_status_dict(s: Any) -> Dict[str, Any]:
    return {
        "notebook_id": getattr(s, "notebook_id", None),
        "is_public": getattr(s, "is_public", None),
        "view_level": _jsonable(getattr(s, "view_level", None)),
        "share_url": getattr(s, "share_url", None),
        "shared_users": _jsonable(getattr(s, "shared_users", None)),
    }


class NotebookLMRPCClient:
    """High-level RPC client (notebooklm-py backend) with management support."""

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

    async def get_response(self) -> str:
        # ``chat.ask`` already returns the completed answer in send_message.
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
    # Compose: copy/merge sources across notebooks
    # ------------------------------------------------------------------ #
    async def copy_source(
        self, from_notebook_id: str, source_id: str, to_notebook_id: str
    ) -> Dict[str, Any]:
        """Copy one source into another notebook.

        Web sources (which carry a ``url``) are re-added by URL; sources without
        a URL (e.g. pasted text or uploads) are re-added as text from their
        extracted full-text content.
        """
        backend = self._require_backend()
        src = await backend.sources.get(from_notebook_id, source_id)
        if src is None:
            raise NavigationError(
                f"Source {source_id} not found in notebook {from_notebook_id}"
            )
        url = getattr(src, "url", None)
        if url:
            new = await backend.sources.add_url(to_notebook_id, url)
        else:
            full = await backend.sources.get_fulltext(from_notebook_id, source_id)
            title = getattr(src, "title", None) or getattr(full, "title", "Untitled")
            content = getattr(full, "content", "") or ""
            new = await backend.sources.add_text(to_notebook_id, title, content)
        return _source_dict(new)

    async def create_notebook_from_sources(
        self, title: str, source_refs: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Create a notebook and copy in sources picked from other notebooks.

        ``source_refs`` is a list of ``{"notebook_id", "source_id"}``. Returns
        the new notebook plus the per-source ``copied`` / ``failed`` outcome, so
        one bad source never aborts the whole merge.
        """
        notebook = await self.create_notebook(title)
        new_id = notebook["id"]
        copied: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for ref in source_refs:
            try:
                copied.append(
                    await self.copy_source(ref["notebook_id"], ref["source_id"], new_id)
                )
            except Exception as exc:  # noqa: BLE001 - report, don't abort the merge
                failed.append({**ref, "error": str(exc)})
        return {"notebook": notebook, "copied": copied, "failed": failed}

    # ------------------------------------------------------------------ #
    # Audio Overview (podcast)
    # ------------------------------------------------------------------ #
    async def generate_audio_overview(
        self,
        notebook_id: str,
        instructions: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Request an Audio Overview (podcast). Generation runs server-side;
        the returned status carries the task and (when ready) the audio URL."""
        backend = self._require_backend()
        status = await backend.artifacts.generate_audio(
            notebook_id, language=language, instructions=instructions
        )
        return _gen_status_dict(status)

    async def list_audio_overviews(self, notebook_id: str) -> List[Dict[str, Any]]:
        """List the Audio Overviews generated for a notebook."""
        backend = self._require_backend()
        return [
            _artifact_dict(a) for a in await backend.artifacts.list_audio(notebook_id)
        ]

    # ------------------------------------------------------------------ #
    # Sharing
    # ------------------------------------------------------------------ #
    async def get_share_status(self, notebook_id: str) -> Dict[str, Any]:
        """Read a notebook's current sharing status (read-only)."""
        backend = self._require_backend()
        return _share_status_dict(await backend.sharing.get_status(notebook_id))

    async def set_notebook_public(
        self, notebook_id: str, public: bool
    ) -> Dict[str, Any]:
        """Toggle public (link) sharing for a notebook."""
        backend = self._require_backend()
        return _share_status_dict(await backend.sharing.set_public(notebook_id, public))

    async def share_notebook_with_user(
        self, notebook_id: str, email: str, permission: str = "viewer"
    ) -> Dict[str, Any]:
        """Share a notebook with a specific person by email."""
        from notebooklm import SharePermission

        perm = getattr(SharePermission, permission.upper(), SharePermission.VIEWER)
        backend = self._require_backend()
        result = await backend.sharing.add_user(notebook_id, email, permission=perm)
        return _share_status_dict(result)

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
