"""Ingestion pipeline (Playbook P3): parse -> map -> review gate -> embed ->
READY. Idempotent: statements/line items are upserted by
(filing, period, type) / (statement, canonical_key) so retries never
double-write.
"""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.ingestion.chunker import chunk_document
from app.ingestion.mapper import MappedItem, map_document
from app.ingestion.parser import parse_pdf
from app.models import (
    Chunk,
    Filing,
    FinancialStatement,
    IngestionJob,
    JobState,
    LineItem,
    StatementStatus,
    StatementType,
)
from app.rag.indexing import embed_and_index

logger = structlog.get_logger("ingestion.pipeline")

STMT_FOR_ITEM = {
    "revenue": "pl", "cogs": "pl", "gross_profit": "pl", "opex": "pl",
    "ebitda": "pl", "dna": "pl", "ebit": "pl", "interest_expense": "pl",
    "other_income": "pl", "pbt": "pl", "tax_expense": "pl", "pat": "pl",
    "shares_outstanding": "pl",
    "cash": "bs", "trade_receivables": "bs", "inventory": "bs",
    "current_assets": "bs", "trade_payables": "bs", "current_liabilities": "bs",
    "st_borrowings": "bs", "lt_debt": "bs", "total_debt": "bs",
    "total_equity": "bs", "ocf": "cf", "capex": "cf", "fcf": "cf",
}


@dataclass
class PipelineReport:
    job_id: str
    state: str
    items: int
    review_items: int
    chunks: int
    conflicts: list[dict]
    unmapped: list[str]


class ProgressReporter:
    """Updates ingestion_jobs state/progress; also usable without a job."""

    def __init__(self, db: AsyncSession, job_id: uuid.UUID | None) -> None:
        self.db = db
        self.job_id = job_id

    async def update(self, state: JobState, progress: int, detail: str) -> None:
        logger.info("ingestion_stage", state=state.value, progress=progress,
                    detail=detail)
        if self.job_id is None:
            return
        job = await self.db.get(IngestionJob, self.job_id)
        if job is None:
            return
        job.state = state
        job.progress = progress
        job.stage_detail = detail
        await self.db.commit()


async def run_pipeline(db: AsyncSession, filing_id: uuid.UUID,
                       job_id: uuid.UUID | None = None,
                       *, llm_assist: bool = True) -> PipelineReport:
    import asyncio
    settings = get_settings()
    reporter = ProgressReporter(db, job_id)
    filing = await db.get(Filing, filing_id)
    if filing is None:
        raise ValueError(f"filing {filing_id} not found")

    await reporter.update(JobState.PARSING, 10, "parsing pages")
    # Parse in a thread so the async event loop is not blocked.
    parsed = await asyncio.to_thread(parse_pdf, filing.file_path)
    filing.num_pages = len(parsed.pages)

    await reporter.update(JobState.EXTRACTING, 30,
                          f"extracted {len(parsed.tables)} tables")
    await reporter.update(JobState.MAPPING, 50, "mapping labels to taxonomy")
    mapped = await map_document(parsed, llm_assist=llm_assist)
    await _upsert_statements(db, filing, mapped.items)

    review = [i for i in mapped.items
              if i.confidence < settings.confidence_review_threshold]
    if review:
        await reporter.update(
            JobState.AWAITING_REVIEW, 70,
            f"{len(review)} items below {settings.confidence_review_threshold} "
            "confidence awaiting human review")
        # Cache parsed doc in filing so _embed_stage can reuse it.
        filing._parsed_cache = parsed  # transient attr — not persisted
        return PipelineReport(job_id=str(job_id) if job_id else "",
                              state=JobState.AWAITING_REVIEW.value,
                              items=len(mapped.items), review_items=len(review),
                              chunks=0, conflicts=mapped.conflicts,
                              unmapped=mapped.unmapped)

    chunks = await _embed_stage(db, filing, reporter, parsed_doc=parsed)
    return PipelineReport(job_id=str(job_id) if job_id else "",
                          state=JobState.READY.value,
                          items=len(mapped.items), review_items=0,
                          chunks=chunks, conflicts=mapped.conflicts,
                          unmapped=mapped.unmapped)


async def continue_after_review(db: AsyncSession, filing_id: uuid.UUID,
                                job_id: uuid.UUID | None = None) -> int:
    """Called by the review API when all low-confidence items are approved."""
    import asyncio
    reporter = ProgressReporter(db, job_id)
    filing = await db.get(Filing, filing_id)
    # Reuse cached parse if available (same process lifetime); else re-parse.
    parsed_doc = getattr(filing, "_parsed_cache", None)
    if parsed_doc is None:
        parsed_doc = await asyncio.to_thread(parse_pdf, filing.file_path)
    chunks = await _embed_stage(db, filing, reporter, parsed_doc=parsed_doc)
    return chunks


async def _embed_stage(db: AsyncSession, filing: Filing,
                       reporter: ProgressReporter, *,
                       parsed_doc=None) -> int:
    import asyncio
    await reporter.update(JobState.EMBEDDING, 85, "chunking + embedding")
    if parsed_doc is None:
        parsed_doc = await asyncio.to_thread(parse_pdf, filing.file_path)
    chunks = chunk_document(parsed_doc)
    count = await embed_and_index(db, filing.id, chunks)
    await reporter.update(JobState.READY, 100, f"{count} chunks indexed")
    filing.status = "ready"
    await db.commit()
    return count


async def _upsert_statements(db: AsyncSession, filing: Filing,
                             items: list[MappedItem]) -> None:
    # Idempotent: clear prior data for this filing, then insert.
    stmt_ids = select(FinancialStatement.id).where(
        FinancialStatement.filing_id == filing.id)
    await db.execute(delete(LineItem).where(LineItem.statement_id.in_(stmt_ids)))
    await db.execute(delete(FinancialStatement).where(
        FinancialStatement.filing_id == filing.id))

    threshold = get_settings().confidence_review_threshold
    statements: dict[tuple[str, str], FinancialStatement] = {}
    for item in items:
        stype = STMT_FOR_ITEM.get(item.canonical_key, "pl")
        key = (item.period, stype)
        if key not in statements:
            # Check if this statement group has any item below review threshold
            has_low_conf = any(
                i.confidence < threshold
                for i in items
                if (i.period, STMT_FOR_ITEM.get(i.canonical_key, "pl")) == key
            )
            stmt = FinancialStatement(
                filing_id=filing.id, company_id=filing.company_id,
                period=item.period, statement_type=StatementType(stype),
                status=StatementStatus.DRAFT if has_low_conf else StatementStatus.APPROVED)
            db.add(stmt)
            await db.flush()
            statements[key] = stmt
        db.add(LineItem(
            statement_id=statements[key].id, canonical_key=item.canonical_key,
            value=round(item.value, 2), unit=item.unit,
            page_no=item.page_no, raw_label=item.raw_label,
            confidence=item.confidence, method=item.method,
            source=item.source))
    await db.commit()


async def job_state(db: AsyncSession, job_id: uuid.UUID) -> dict:
    job = await db.get(IngestionJob, job_id)
    if job is None:
        raise ValueError("job not found")
    return {"job_id": str(job.id), "filing_id": str(job.filing_id),
            "state": job.state.value if hasattr(job.state, "value") else str(job.state),
            "progress": job.progress, "stage_detail": job.stage_detail,
            "error": job.error, "retry_count": job.retry_count}
