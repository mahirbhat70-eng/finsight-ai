"""Global error envelope: {error: {code, message, request_id}}."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_request_id


class AppError(Exception):
    """Base class for expected, user-facing errors."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message,
                               "request_id": get_request_id()}},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        # Log the traceback server-side; never leak internals to the client.
        import structlog
        structlog.get_logger("errors").error("unhandled_exception",
                                             error=repr(exc), request_id=get_request_id())
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error",
                               "message": "An unexpected error occurred.",
                               "request_id": get_request_id()}},
        )
