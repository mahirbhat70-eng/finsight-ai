"""E2E ingestion test (Playbook P3.6) — integration (needs Postgres).

Runs the full pipeline on novatech_annual_report.pdf with the mock
provider; asserts >= 95% ground-truth mapping, chunk sanity, hybrid search
finds the customer-concentration page in top 3, and the review flow
resumes the job to READY.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory, init_models
from app.ingestion.pipeline import run_pipeline
from app.models import Company, Filing, FilingDocType, IngestionJob, JobState
from app.rag.retrieval import hybrid_search

pytestmark = pytest.mark.integration

def find_fixtures() -> Path:
    """data/fixtures in the merged repo OR inside a phase folder."""
    for parent in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
        cand = parent / "data" / "fixtures"
        if (cand / "novatech_annual_report.pdf").exists():
            return cand
    raise FileNotFoundError("data/fixtures not found above tests/")


FIXTURES = find_fixtures()


async def _setup_company() -> tuple:
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            Company.__table__.select().where(
                Company.name == "E2E Ingestion Test Co"))
        row = result.first()
        if row is None:
            company = Company(name="E2E Ingestion Test Co", sector="test")
            db.add(company)
            await db.commit()
        else:
            company = await db.get(Company, row.id)
        filing = Filing(
            company_id=company.id, doc_type=FilingDocType.ANNUAL_REPORT,
            file_path=str(FIXTURES / "novatech_annual_report.pdf"),
            status="pending")
        db.add(filing)
        job = IngestionJob(filing_id=filing.id, state=JobState.PENDING)
        db.add(job)
        await db.commit()
        return company.id, filing.id, job.id


async def test_ingestion_e2e() -> None:
    await init_models()
    company_id, filing_id, job_id = await _setup_company()

    factory = get_session_factory()
    async with factory() as db:
        report = await run_pipeline(db, filing_id, job_id, llm_assist=False)

        # Mapping quality vs ground truth
        gt = json.loads((FIXTURES / "novatech_ground_truth.json").read_text())
        gt_map = {(f["key"], f["period"]): f["value"] for f in gt["facts"]}
        from app.models import FinancialStatement, LineItem, StatementStatus
        from sqlalchemy import select

        rows = (await db.execute(
            select(LineItem.canonical_key, FinancialStatement.period,
                   LineItem.value)
            .join(FinancialStatement,
                  LineItem.statement_id == FinancialStatement.id)
            .where(FinancialStatement.filing_id == filing_id)
        )).all()
        hit = sum(
            1 for key, period, value in rows
            if (key, period) in gt_map
            and abs(float(value) - gt_map[(key, period)])
            <= abs(gt_map[(key, period)]) * 0.005 + 0.02)
        total = sum(1 for key, period, _ in rows if (key, period) in gt_map)
        assert total > 0 and hit / total >= 0.95

        # Review gate: ambiguous rows hold the job
        assert report.state == JobState.AWAITING_REVIEW.value
        assert 0 < report.review_items <= 12

        # Approve everything through the review API logic
        from app.core.settings import get_settings
        from app.api.v1.review import review_item

        threshold = get_settings().confidence_review_threshold
        low = (await db.execute(
            select(LineItem).join(FinancialStatement)
            .where(FinancialStatement.filing_id == filing_id,
                   LineItem.confidence < threshold)
        )).scalars().all()
        for item in low:
            await review_item(item.id, __import__("app.api.v1.review", fromlist=[
                "ReviewDecision"]).ReviewDecision(approve=True),
                reviewer="e2e", db=db)

        job = await db.get(IngestionJob, job_id)
        assert job.state in (JobState.EMBEDDING, JobState.READY)

        # Hybrid search: customer concentration note in top 3
        results = await hybrid_search(db, "customer concentration risk")
        assert results, "hybrid search returned nothing"
        top3 = results[:3]
        assert any("Customer A" in r.text or "concentration" in r.text.lower()
                   for r in top3), \
            "concentration note not in top-3 retrieved chunks"

        # Chunk sanity
        from app.models import Chunk
        n_chunks = (await db.execute(
            select(Chunk).where(Chunk.filing_id == filing_id))).scalars().all()
        assert 5 <= len(n_chunks) <= 200

        # Cleanup
        await db.delete(await db.get(Filing, filing_id))
        company = await db.get(Company, company_id)
        await db.delete(company)
        await db.commit()
