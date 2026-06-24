"""
Rate limiting in-memory por IP para rutas de autenticación.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Limita requests a rutas de auth por IP en ventanas deslizantes."""

    def __init__(self, app, *, path_limits: dict[str, tuple[int, int]] | None = None) -> None:
        super().__init__(app)
        # path suffix -> (max_requests, window_seconds)
        self.path_limits = path_limits or {"/api/v1/auth/login": (10, 60)}
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _is_limited(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= limit:
            return True
        hits.append(now)
        return False

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        rule = self.path_limits.get(path)
        if rule and request.method == "POST":
            limit, window = rule
            ip = self._client_ip(request)
            key = f"{path}:{ip}"
            if self._is_limited(key, limit, window):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Demasiados intentos. Intentá de nuevo más tarde."},
                )
        return await call_next(request)
