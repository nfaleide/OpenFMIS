"""Simple in-memory rate limiting middleware.

Uses a sliding-window counter per client IP. Suitable for single-process
deployments; swap to Redis-backed storage for multi-worker setups.
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter keyed on client IP.

    Args:
        app: ASGI application
        requests_per_minute: max requests allowed per IP per minute (default 120)
    """

    def __init__(self, app, requests_per_minute: int = 120) -> None:  # noqa: ANN001
        super().__init__(app)
        self.rpm = requests_per_minute
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for health checks and static files
        path = request.url.path
        if path in ("/health", "/") or path.startswith("/static"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - 60.0

        # Prune expired entries
        bucket = self._buckets[client_ip]
        self._buckets[client_ip] = bucket = [t for t in bucket if t > window_start]

        if len(bucket) >= self.rpm:
            retry_after = int(60 - (now - bucket[0])) + 1
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.rpm - len(bucket)))
        return response
