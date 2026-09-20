"""Rate limits (Phase 7): default 60/min; copilot 10/min; exports 5/min.
429 responses carry the error envelope + Retry-After."""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from app.core.logging import get_request_id
from app.core.settings import get_settings


def build_limiter() -> Limiter:
    settings = get_settings()
    return Limiter(
        key_func=_key, default_limits=[settings.rate_limit_default],
        headers_enabled=True)


def _key(request) -> str:  # API key > bearer > remote address
    return (request.headers.get("X-API-Key")
            or request.headers.get("Authorization", "")
            or get_remote_address(request))


def register_rate_limit_handler(app) -> None:
    @app.exception_handler(RateLimitExceeded)
    async def _handler(request, exc):  # noqa: ANN001, RUF029
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
            content={"error": {"code": "rate_limited",
                               "message": "too many requests — slow down",
                               "request_id": get_request_id()}})
