"""Copilot tests (Playbook P4.3/P4.5): unit parts of the orchestrator plus
integration tests for the sync/SSE contracts and qa_logs persistence.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.orchestrator import (
    assemble_context,
    build_metrics_digest,
    classify_intent,
)
from app.rag.retrieval import RetrievedChunk

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def _series() -> tuple[dict, list[str]]:
    import json

    payload = json.loads((FIXTURES / "novatech_statements.json").read_text())
    return payload["items"], payload["periods"]


def test_intent_classification() -> None:
    assert classify_intent("What was revenue in FY2025?") == "metric_question"
    assert classify_intent("What was EBITDA in FY2024?") == "metric_question"
    assert classify_intent("Why did EBITDA margin decline in FY2023?") == "both"
    assert classify_intent("What are the related party transactions?") == \
        "narrative_question"
    assert classify_intent("How is leverage trending?") in ("metric_question", "both")


def test_metrics_digest_deterministic() -> None:
    series, periods = _series()
    digest = build_metrics_digest(series, periods)
    assert "revenue" in digest
    assert "7,340" in digest  # latest revenue INR cr
    assert "ebitda_margin" in digest
    # deterministic: same input -> same bytes
    assert digest == build_metrics_digest(series, periods)


def test_context_assembly_contains_sources_and_budget() -> None:
    chunks = [RetrievedChunk(chunk_id=f"c{i}", filing_id="f", page_no=i,
                             section="MD&A", text="filler text " * 800,
                             score=0.5, sources=["vector"]) for i in range(10)]
    prompt = assemble_context(chunks, "digest line", "question?")
    assert "[S1] id=c0" in prompt
    assert "FACTS" in prompt
    # budget: 10 big chunks cannot all fit in 6k tokens
    assert prompt.count("[S") < 10


@pytest.mark.integration
async def test_copilot_sync_contract_and_retry() -> None:
    """Full loop against a seeded DB with a stubbed provider: a bad answer
    triggers exactly one regeneration; the final payload carries the
    verification verdict and qa_logs is written."""
    import json
    import uuid as uuid_mod

    from sqlalchemy import select

    from app.db.session import get_session_factory, init_models
    from app.models import Company, QaLog
    from app.rag import orchestrator

    await init_models()
    calls = {"n": 0}

    class StubProvider:
        name = "stub"
        model = "stub-1"

        async def complete_json(self, prompt, schema, *, system=None,
                                temperature=0.1):
            calls["n"] += 1
            if calls["n"] == 1:  # first attempt: ungrounded citation
                return schema.model_validate({
                    "answer": "Revenue was Rs 9,999.0 crore [S1].",
                    "citations": [{"chunk_id": "ghost", "doc": "x",
                                   "page_no": 1, "quote": "nothing"}],
                    "confidence": 0.9, "insufficient_evidence": False})
            # second attempt: cite the real chunk parsed from the prompt
            match = re.search(r"\[S1\] id=([0-9a-f-]+) page=(\d+)", prompt)
            chunk_id, page = match.group(1), int(match.group(2))
            text_match = re.search(
                r"\[S1\] id=[0-9a-f-]+ page=\d+ section=[^\n]*\n(.{20,200})", prompt)
            quote = (text_match.group(1) if text_match else "revenue")[:200]
            return schema.model_validate({
                "answer": f"Revenue was Rs 7,340.0 crore [S1].",
                "citations": [{"chunk_id": chunk_id, "doc": "annual_report.pdf",
                               "page_no": page, "quote": quote}],
                "confidence": 0.9, "insufficient_evidence": False})

        async def embed(self, texts):
            from app.llm.mock import MockProvider

            return [MockProvider._hash_vector(t) for t in texts]

    original = orchestrator.get_llm_provider
    orchestrator.get_llm_provider = lambda: StubProvider()
    try:
        factory = get_session_factory()
        async with factory() as db:
            company = (await db.execute(
                select(Company).where(Company.name == "NovaTech Industries Ltd"))
            ).scalars().first()
            assert company is not None, "run `make seed` first"
            payload = await orchestrator.answer_question(
                db, company.id, "What was NovaTech's revenue in FY2025?")
            assert calls["n"] == 2, "exactly one regeneration must happen"
            assert payload["answer"]
            assert payload["verification"]["verdict"] == "grounded"
            assert payload["citations"][0]["page_no"] > 0
            rows = (await db.execute(
                select(QaLog).where(QaLog.company_id == company.id)
                .order_by(QaLog.created_at.desc()))).scalars().first()
            assert rows is not None and rows.grounded
    finally:
        orchestrator.get_llm_provider = original
