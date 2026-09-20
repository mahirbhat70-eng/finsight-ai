"""Peers API (Playbook P6.1/P6.2): CRUD, comparison table, radar payload,
grounded peer narrative (LLM explains drivers, never ranks a winner).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.finmod.peers import build_comparison, implied_valuation_range, radar_payload
from app.finmod.ratios import compute_metrics
from app.models import Company, Peer, PeerMetric
from app.services.series import load_company_series

router = APIRouter(prefix="/companies", tags=["peers"])
logger = structlog.get_logger("api.peers")


async def _target_metrics(db: AsyncSession, company_id: uuid.UUID
                          ) -> tuple[dict[str, float | None], dict, list[str]]:
    series, periods = await load_company_series(db, company_id)
    if not series:
        raise HTTPException(404, "no approved statements for this company")
    table = compute_metrics(series, periods)  # type: ignore[arg-type]
    metrics: dict[str, float | None] = {}
    for key, row in table._rows.items():  # noqa: SLF001
        latest = next(iter(reversed(row.values())), None)
        metrics[key] = latest.value if latest else None
    return metrics, series, periods  # type: ignore[return-value]


async def _peer_rows(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    peers = (await db.execute(
        select(Peer).where(Peer.company_id == company_id, Peer.name != "__context__")
    )).scalars().all()
    out: list[dict] = []
    for peer in peers:
        rows = (await db.execute(
            select(PeerMetric).where(PeerMetric.peer_id == peer.id)
        )).scalars().all()
        metrics = {m.metric_key: m.value for m in rows}
        out.append({"name": peer.name, "metrics": metrics,
                    "ev_ebitda": metrics.get("ev_ebitda")})
    return out


@router.get("/{company_id}/peers")
async def get_comparison(company_id: uuid.UUID,
                         db: AsyncSession = Depends(get_db)) -> dict:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    metrics, series, periods = await _target_metrics(db, company_id)
    peers = await _peer_rows(db, company_id)
    comparison = build_comparison(metrics, peers)
    multiples = [p["ev_ebitda"] for p in peers if p.get("ev_ebitda")]
    comparison["implied_valuation"] = implied_valuation_range(
        series["ebitda"][-1], multiples)
    comparison["radar"] = radar_payload(metrics, peers)
    return comparison


class PeerIn(BaseModel):
    name: str
    metrics: dict[str, float]


@router.put("/{company_id}/peers")
async def upsert_peer(company_id: uuid.UUID, payload: PeerIn,
                      db: AsyncSession = Depends(get_db)) -> dict:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    peer = (await db.execute(
        select(Peer).where(Peer.company_id == company_id, Peer.name == payload.name)
    )).scalars().first()
    if peer is None:
        peer = Peer(company_id=company_id, name=payload.name)
        db.add(peer)
        await db.flush()
    await db.execute(select(PeerMetric).where(PeerMetric.peer_id == peer.id))
    for m in (await db.execute(
            select(PeerMetric).where(PeerMetric.peer_id == peer.id))).scalars():
        await db.delete(m)
    for key, value in payload.metrics.items():
        db.add(PeerMetric(peer_id=peer.id, metric_key=key, value=value,
                          period="FY2025", source="manual entry"))
    await db.commit()
    return {"peer_id": str(peer.id), "name": payload.name,
            "metrics": len(payload.metrics)}


class NarrativeIn(BaseModel):
    question: str = "Explain the margin position versus peers and the drivers"


@router.post("/{company_id}/peers/narrative")
async def peer_narrative(company_id: uuid.UUID, payload: NarrativeIn,
                         db: AsyncSession = Depends(get_db)) -> dict:
    """Grounded explanation of differences; the LLM never picks a winner."""
    from app.rag.grounding import verify_answer
    from app.rag.prompts import PEER_NARRATIVE_SYSTEM_PROMPT_V1
    from app.rag.retrieval import hybrid_search
    from app.llm.base import get_llm_provider
    from app.schemas.copilot import CopilotAnswer

    metrics, series, periods = await _target_metrics(db, company_id)
    peers = await _peer_rows(db, company_id)
    comparison = build_comparison(metrics, peers)

    table_lines = ["metric | target | peer median"]
    for row in comparison["metrics"]:
        table_lines.append(
            f"{row['label']} | {row['target'] if row['target'] is not None else '—'} | "
            f"{row['median'] if row['median'] is not None else '—'}")
    chunks = await hybrid_search(db, payload.question, top_k=5)
    context = "\n".join(
        f"[S{i}] page={c.page_no}\n{c.text}" for i, c in enumerate(chunks, start=1))
    prompt = (f"QUESTION: {payload.question}\n\nCOMPARISON (peer values are "
              f"external provided data):\n" + "\n".join(table_lines)
              + "\n\nFILING CONTEXT (target company only):\n" + context)

    provider = get_llm_provider()
    try:
        answer = await provider.complete_json(
            prompt, CopilotAnswer, system=PEER_NARRATIVE_SYSTEM_PROMPT_V1,
            temperature=0.1)
    except Exception:  # noqa: BLE001 — provider failure degrades gracefully
        answer = CopilotAnswer(
            answer="Peer narrative unavailable with the current provider.",
            insufficient_evidence=True)
    verification = verify_answer(answer, chunks, [])
    return {"answer": answer.answer,
            "citations": [c.model_dump() for c in answer.citations],
            "verification": verification.model_dump()}
