"""Request-id middleware: binds a structlog request_id per request."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import bind_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        bind_request_id(rid)
        start = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        structlog.get_logger("http").info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=rid,
        )
        return response
