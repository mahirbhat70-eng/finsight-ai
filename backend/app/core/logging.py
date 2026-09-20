"""structlog JSON logging with request_id correlation (Playbook Phase 0).

Every log line is grep-able by request_id; prod emits JSON, dev emits a
readable console renderer. Retrofitting logs is misery — this exists from
day 0.
"""

import contextvars
import logging
import uuid
from typing import Any

import structlog

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_shared_processors: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
]


def bind_request_id(rid: str | None = None) -> str:
    rid = rid or uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def get_request_id() -> str:
    return request_id_var.get()


def configure_logging(env: str = "dev", level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper()))
    renderer = (
        structlog.dev.ConsoleRenderer()
        if env == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[*_shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
