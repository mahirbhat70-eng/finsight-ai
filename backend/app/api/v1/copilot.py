"""Copilot endpoints (Playbook P4.5):
POST /api/v1/copilot/query       (SSE: token deltas, then done event)
POST /api/v1/copilot/query_sync  (JSON — used by tests and the eval harness)
"""

import json
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db
from app.models import Company, QaLog
from app.rag.orchestrator import answer_question
from app.schemas.copilot import CopilotQuery

router = APIRouter(prefix="/copilot", tags=["copilot"])
logger = structlog.get_logger("api.copilot")


async def _validate(db: AsyncSession, payload: CopilotQuery) -> uuid.UUID:
    company_id = uuid.UUID(payload.company_id)
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    return company_id


@router.post("/query_sync")
async def query_sync(payload: CopilotQuery,
                     db: AsyncSession = Depends(get_db)) -> dict:
    company_id = await _validate(db, payload)
    try:
        return await answer_question(db, company_id, payload.question)
    except ValueError as exc:
        raise AppError("copilot_input_error", str(exc), 422) from exc


@router.post("/query")
async def query(payload: CopilotQuery,
                db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """SSE: `token` events with deltas, `done` event with the structured
    payload + citations + verification verdict. Non-streaming work happens
    up front (retrieval + LLM + verification), then deltas replay."""
    company_id = await _validate(db, payload)
    try:
        result = await answer_question(db, company_id, payload.question)
    except ValueError as exc:
        raise AppError("copilot_input_error", str(exc), 422) from exc

    async def event_stream() -> AsyncIterator[str]:
        answer_text = result["answer"]
        for i in range(0, len(answer_text), 24):
            delta = answer_text[i:i + 24]
            yield f"event: token\ndata: {json.dumps({'delta': delta})}\n\n"
        yield f"event: done\ndata: {json.dumps(result)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/sessions/{conversation_id}")
async def session_history(conversation_id: str,
                          db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Q&A audit trail per conversation (qa_logs ordered by time)."""
    rows = (await db.execute(
        select(QaLog).order_by(QaLog.created_at)
    )).scalars().all()  # demo: global trail; partition by conversation in prod
    return [{"question": q.question, "answer": q.answer,
             "grounded": q.grounded, "latency_ms": q.latency_ms,
             "citations": q.citations} for q in rows]
