"""Copilot orchestrator (Playbook P4.2): intent classification (keyword map,
no LLM), deterministic metrics digest, context assembly with budget,
history window (6 turns), one verifier-feedback retry, qa_logs + llm_calls
persistence.
"""

import re
import time
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_session_factory
from app.finmod.ratios import compute_metrics
from app.llm.base import drain_llm_calls, get_llm_provider
from app.models import LlmCall, QaLog
from app.rag.grounding import verify_answer
from app.rag.prompts import COPILOT_SYSTEM_PROMPT_V1, COPILOT_USER_TEMPLATE
from app.rag.retrieval import RetrievedChunk, hybrid_search
from app.schemas.copilot import CopilotAnswer
from app.services.series import load_company_series

logger = structlog.get_logger("rag.orchestrator")

METRIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "growth": ("growth", "cagr", "grew", "increase", "decline", "declined", "yoy"),
    "margin": ("margin", "ebitda", "gross", "profitability", "ebit"),
    "returns": ("roe", "roic", "return on", "roa"),
    "cash": ("fcf", "free cash", "ocf", "operating cash", "cash conversion",
             "cash", "capex", "capital expenditure"),
    "debt": ("debt", "leverage", "borrowings", "net debt", "interest"),
    "liquidity": ("current ratio", "quick ratio", "liquidity"),
    "working_capital": ("receivable", "payable", "inventory", "working capital",
                        "dso", "days"),
    "basics": ("revenue", "sales", "pat", "profit", "equity", "share"),
}

DIGEST_KEYS = ("revenue", "ebitda", "pat", "ocf", "capex", "fcf", "cash",
               "total_debt", "total_equity", "trade_receivables", "inventory")
RATIO_DIGEST_KEYS = ("revenue_growth", "ebitda_margin", "pat_margin", "roe",
                     "roic", "debt_to_equity", "net_debt_to_ebitda",
                     "current_ratio", "interest_cover", "dso", "ocf_ebitda")
CONTEXT_BUDGET_TOKENS = 6000


def classify_intent(question: str) -> str:
    """{metric_question, narrative_question, both} via keywords (no LLM)."""
    lowered = question.lower()
    hit = {family for family, words in METRIC_KEYWORDS.items()
           if any(w in lowered for w in words)}
    narrative = bool(re.search(r"why|how|explain|describe|what happened|story|"
                               r"drivers|trend", lowered))
    if hit and narrative:
        return "both"
    if hit:
        return "metric_question"
    return "narrative_question"


def build_metrics_digest(series: dict[str, list], periods: list[str]) -> str:
    """Deterministic FACTS table: latest values + 3-year trend."""
    lines = [f"company periods: {', '.join(periods)}"]
    for key in DIGEST_KEYS:
        values = series.get(key)
        if not values:
            continue
        trend = " -> ".join(f"{v:,.1f}" for v in values[-3:] if v is not None)
        lines.append(f"{key}: {trend} INR_cr")
    table = compute_metrics(series, periods)
    for key in RATIO_DIGEST_KEYS:
        row = table._rows.get(key, {})  # noqa: SLF001
        latest = next(iter(reversed(row.values())), None)  # latest period
        if latest is None or latest.value is None:
            continue
        if latest.unit == "percent":
            lines.append(f"{key}: {latest.value * 100:.1f}% (latest)")
        else:
            lines.append(f"{key}: {latest.value:.2f} (latest)")
    return "\n".join(lines)


def digest_value_pool(series: dict[str, list], periods: list[str]) -> list[float]:
    """All numeric values the answer's numbers are allowed to trace to."""
    pool: list[float] = []
    for values in series.values():
        pool.extend(v for v in values if v is not None)
    table = compute_metrics(series, periods)
    for row in table._rows.values():  # noqa: SLF001
        pool.extend(res.value * 100 for res in row.values()
                    if res.value is not None and res.unit == "percent")
    return pool


def assemble_context(chunks: list[RetrievedChunk], digest: str,
                      question: str, history: list[dict] | None = None
                      ) -> str:
    settings = get_settings()
    context_blocks: list[str] = []
    budget = CONTEXT_BUDGET_TOKENS
    for idx, chunk in enumerate(chunks, start=1):
        block = (f"[S{idx}] id={chunk.chunk_id} page={chunk.page_no} "
                 f"section={chunk.section}\n{chunk.text}")
        tokens = len(block) // 4
        if tokens > budget:
            block = block[: budget * 4]
            context_blocks.append(block)
            break
        context_blocks.append(block)
        budget -= tokens
    history_lines = ""
    if history:
        recent = history[-6:]
        history_lines = "CONVERSATION (last 6 turns):\n" + "\n".join(
            f"{turn['role']}: {turn['content'][:300]}" for turn in recent) + "\n\n"
    return COPILOT_USER_TEMPLATE.format(
        question=question, digest=digest, context="\n\n".join(context_blocks),
        history=history_lines)


async def answer_question(db: AsyncSession, company_id: uuid.UUID,
                          question: str,
                          history: list[dict] | None = None) -> dict:
    """Full grounded Q&A cycle. Returns the answer payload + verification."""
    settings = get_settings()
    started = time.monotonic()

    series, periods = await load_company_series(db, company_id)
    if not series:
        raise ValueError("no approved statements for this company")
    digest = build_metrics_digest(series, periods)  # type: ignore[arg-type]
    value_pool = digest_value_pool(series, periods)  # type: ignore[arg-type]

    chunks = await hybrid_search(db, question, top_k=settings.copilot_top_k)
    prompt = assemble_context(chunks, digest, question, history)

    provider = get_llm_provider()
    answer: CopilotAnswer | None = None
    verification = None
    for attempt in (1, 2):  # one regeneration with verifier feedback
        if attempt == 2 and verification is not None:
            prompt = (f"{prompt}\n\n{verification.feedback}")
        try:
            answer = await provider.complete_json(
                prompt, CopilotAnswer, system=COPILOT_SYSTEM_PROMPT_V1,
                temperature=0.1)
        except Exception as exc:  # noqa: BLE001
            logger.error("copilot_llm_failed", attempt=attempt, error=repr(exc))
            answer = CopilotAnswer(
                answer="could not produce a valid structured answer",
                insufficient_evidence=True)
        verification = verify_answer(answer, chunks, value_pool)
        if verification.grounded or answer.insufficient_evidence:
            break

    latency_ms = int((time.monotonic() - started) * 1000)
    tokens = 0
    for call in drain_llm_calls():
        tokens += call["prompt_tokens"] + call["completion_tokens"]
        db.add(LlmCall(**{k: v for k, v in call.items() if k != "created_at"}))

    payload = {
        "answer": answer.answer,
        "citations": [c.model_dump() for c in answer.citations],
        "retrieved": [c.chunk_id for c in chunks],
        "metrics_used": [m.model_dump() for m in answer.metrics_used],
        "confidence": answer.confidence,
        "insufficient_evidence": answer.insufficient_evidence,
        "verification": verification.model_dump(),
        "latency_ms": latency_ms,
        "tokens": tokens,
    }
    db.add(QaLog(
        company_id=company_id, question=question, answer=answer.answer,
        citations=payload["citations"], grounded=verification.grounded,
        latency_ms=latency_ms, tokens=tokens))
    await db.commit()
    logger.info("copilot_answer", question=question[:80],
                verdict=verification.verdict, latency_ms=latency_ms)
    return payload
