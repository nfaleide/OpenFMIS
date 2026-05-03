"""Request logging middleware — structured audit trail for all API calls."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("openfmis.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, duration, and caller identity for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status = response.status_code if response else 500
            # Extract user identity from JWT state if available
            user = getattr(request.state, "user_id", None) if hasattr(request, "state") else None
            client_ip = request.client.host if request.client else "-"
            log.info(
                "%s %s %s %dms user=%s ip=%s",
                request.method,
                request.url.path,
                status,
                duration_ms,
                user or "-",
                client_ip,
            )
