"""Security middleware for NotebookLM MCP server."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .monitoring import metrics_collector


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware enforcing API key authentication."""

    def __init__(
        self,
        app,
        *,
        api_keys: Iterable[str],
        header: str = "x-api-key",
        allow_bearer: bool = True,
        exempt_paths: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__(app)
        self._api_keys = {key.strip() for key in api_keys if key and key.strip()}
        self._header = (header or "x-api-key").strip() or "x-api-key"
        self._allow_bearer = allow_bearer
        self._exempt_paths = {
            self._normalise_path(path)
            for path in (exempt_paths or [])
            if path is not None
        }

    @staticmethod
    def _normalise_path(path: str) -> str:
        cleaned = path.strip()
        if not cleaned:
            return "/"
        if not cleaned.startswith("/"):
            cleaned = f"/{cleaned}"
        if cleaned != "/" and cleaned.endswith("/"):
            cleaned = cleaned[:-1]
        return cleaned

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        path = self._normalise_path(str(request.url.path))
        if path in self._exempt_paths:
            return await call_next(request)

        provided_key = request.headers.get(self._header)
        if not provided_key and self._allow_bearer:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.lower().startswith("bearer "):
                provided_key = auth_header[7:]

        if not provided_key or provided_key not in self._api_keys:
            metrics_collector.record_auth_failure()
            logger.warning("Rejected request with missing or invalid API key")
            return JSONResponse(
                {"detail": "Missing or invalid API key"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="NotebookLM MCP"'},
            )

        return await call_next(request)


__all__ = ["APIKeyMiddleware"]
