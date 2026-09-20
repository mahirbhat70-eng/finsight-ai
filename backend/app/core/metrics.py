"""Observability (Phase 7): Prometheus metrics + custom LLM counters +
/api/v1/usage (cost panel: tokens/calls by day)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

try:  # prometheus_client is a light dep; degrade gracefully without it
    from prometheus_client import Counter

    LLM_CALLS = Counter("llm_calls_total", "LLM calls by provider and model",
                        ["provider", "model"])
    LLM_TOKENS = Counter("llm_tokens_total", "LLM tokens by direction",
                         ["provider", "direction"])
except ImportError:  # pragma: no cover
    class _Noop:
        def labels(self, *a, **kw):
            return self

        def inc(self, *a, **kw):
            return None

    LLM_CALLS = LLM_TOKENS = _Noop()


def instrument_app(app) -> None:
    """Expose /metrics with default HTTP metrics (prometheus format)."""
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False)


async def usage_summary(db: AsyncSession) -> dict:
    """llm_calls summarized by day for the admin cost panel."""
    from datetime import UTC, datetime, timedelta

    since = datetime.now(UTC).replace(hour=0, minute=0, second=0) - timedelta(days=6)
    from app.models import LlmCall

    rows = (await db.execute(
        select(
            func.date_trunc("day", LlmCall.created_at).label("day"),
            func.count().label("calls"),
            func.sum(LlmCall.prompt_tokens + LlmCall.completion_tokens).label("tokens"),
        ).where(LlmCall.created_at >= since).group_by("day").order_by("day")
    )).all()
    return {
        "days": [
            {"day": str(r.day), "calls": r.calls,
             "tokens": int(r.tokens or 0)} for r in rows
        ],
        "total_calls": sum(r.calls for r in rows),
        "total_tokens": sum(int(r.tokens or 0) for r in rows),
    }
