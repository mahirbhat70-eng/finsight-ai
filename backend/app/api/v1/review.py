"""Review queue (Playbook P3.4): low-confidence draft items; approve with
optional correction updates value + canonical_key; when all items in a
statement are approved, the statement goes approved and the job continues
to EMBEDDING.

Bulk operations (added for efficiency):
  POST /review/bulk  —  approve_all | reject_unmapped | approve_above:<float>
"""

import sys
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_db
from app.models import (
    Company,
    Filing,
    FinancialStatement,
    IngestionJob,
    JobState,
    LineItem,
    StatementStatus,
)

router = APIRouter(prefix="/review", tags=["review"])
logger = structlog.get_logger("api.review")


@router.get("/queue")
async def review_queue(db: AsyncSession = Depends(get_db),
                       company_id: uuid.UUID | None = None,
                       limit: int = 100) -> list[dict]:
    threshold = get_settings().confidence_review_threshold
    stmt = (
        select(LineItem, FinancialStatement, Filing, Company)
        .join(FinancialStatement,
              LineItem.statement_id == FinancialStatement.id)
        .join(Filing, FinancialStatement.filing_id == Filing.id)
        .join(Company, FinancialStatement.company_id == Company.id)
        .where(FinancialStatement.status == StatementStatus.DRAFT,
               LineItem.confidence < threshold)
        .order_by(LineItem.confidence)
        .limit(limit)
    )
    if company_id is not None:
        stmt = stmt.where(FinancialStatement.company_id == company_id)
    rows = (await db.execute(stmt)).all()
    return [{
        "item_id": str(item.id),
        "company": company.name,
        "company_id": str(company.id),
        "filing_id": str(filing.id),
        "period": statement.period,
        "statement_type": statement.statement_type.value
        if hasattr(statement.statement_type, "value") else str(statement.statement_type),
        "canonical_key": item.canonical_key,
        "raw_label": item.raw_label,
        "value": float(item.value),
        "unit": item.unit,
        "confidence": item.confidence,
        "method": item.method,
        "page_no": item.page_no,
    } for item, statement, filing, company in rows]


class ReviewDecision(BaseModel):
    approve: bool = True
    value: float | None = Field(None, description="corrected value")
    canonical_key: str | None = Field(None, description="corrected canonical key")


@router.post("/items/{item_id}")
async def review_item(item_id: uuid.UUID, decision: ReviewDecision,
                      reviewer: str = "analyst",
                      db: AsyncSession = Depends(get_db)) -> dict:
    item = await db.get(LineItem, item_id)
    if item is None:
        raise HTTPException(404, "line item not found")

    if decision.approve:
        if decision.value is not None:
            item.value = round(decision.value, 2)
        if decision.canonical_key:
            from app.finmod.taxonomy import ALL_KEYS

            if decision.canonical_key not in ALL_KEYS:
                raise HTTPException(422, "unknown canonical key")
            item.canonical_key = decision.canonical_key
        item.confidence = 1.0
        item.approved_by = reviewer
    else:
        await db.delete(item)
    await db.commit()

    # Statement completes when no low-confidence items remain
    statement = await db.get(FinancialStatement, item.statement_id)
    remaining = await _remaining_low_conf(db, statement.id)
    if remaining == 0 and decision.approve:
        statement.status = StatementStatus.APPROVED
        await db.commit()
        await _continue_job_if_clear(db, statement.filing_id)
    logger.info("review_decision", item_id=str(item_id),
                approved=decision.approve, remaining=remaining)
    return {"item_id": str(item_id), "approved": decision.approve,
            "remaining_in_statement": remaining,
            "statement_status": statement.status.value
            if hasattr(statement.status, "value") else str(statement.status)}


async def _remaining_low_conf(db: AsyncSession, statement_id: uuid.UUID) -> int:
    threshold = get_settings().confidence_review_threshold
    from sqlalchemy import func

    return (await db.execute(
        select(func.count()).select_from(LineItem).where(
            LineItem.statement_id == statement_id,
            LineItem.confidence < threshold)
    )).scalar_one()


async def _continue_job_if_clear(db: AsyncSession, filing_id: uuid.UUID) -> None:
    """If every draft statement for the filing is approved, resume the job."""
    threshold = get_settings().confidence_review_threshold
    pending = (await db.execute(
        select(LineItem.id).join(FinancialStatement)
        .where(FinancialStatement.filing_id == filing_id,
               FinancialStatement.status == StatementStatus.DRAFT,
               LineItem.confidence < threshold)
    )).all()
    if pending:
        return

    job = (await db.execute(
        select(IngestionJob).where(IngestionJob.filing_id == filing_id)
        .order_by(IngestionJob.created_at.desc())
    )).scalars().first()
    if job is None or job.state != JobState.AWAITING_REVIEW:
        return

    from app.ingestion.pipeline import continue_after_review
    job.state = JobState.EMBEDDING
    job.stage_detail = "resumed after review"
    await db.commit()
    if get_settings().app_env in ("test", "testing") or "pytest" in sys.modules:
        await continue_after_review(db, filing_id, job.id)
    else:
        try:
            from app.ingestion.worker import enqueue_ingestion
            await enqueue_ingestion(job.id)
        except Exception:  # noqa: BLE001 — no redis: run inline (dev)
            await continue_after_review(db, filing_id, job.id)


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------

class BulkAction(BaseModel):
    """Bulk review action.

    action:
      'approve_all'           — approve every pending review item as-is.
      'reject_unmapped'       — delete all items whose canonical_key starts
                                with 'unmapped:' (ambiguous rows).
      'approve_above'         — approve all items with confidence >= threshold.
    threshold: used only for 'approve_above' (0.0 – 1.0).
    company_id: optional filter; None means all companies.
    filing_id:  optional filter; None means all filings.
    """
    action: str = Field(..., pattern=r"^(approve_all|reject_unmapped|approve_above)$")
    threshold: float = Field(0.7, ge=0.0, le=1.0)
    company_id: uuid.UUID | None = None
    filing_id: uuid.UUID | None = None


class BulkResult(BaseModel):
    action: str
    approved: int = 0
    rejected: int = 0
    filings_resumed: list[str] = []


@router.post("/bulk", response_model=BulkResult)
async def bulk_review(body: BulkAction,
                      db: AsyncSession = Depends(get_db)) -> BulkResult:
    """Resolve many low-confidence items in one call."""
    threshold = get_settings().confidence_review_threshold
    result = BulkResult(action=body.action)

    # Build the base query for pending items.
    base = (
        select(LineItem)
        .join(FinancialStatement, LineItem.statement_id == FinancialStatement.id)
        .where(
            FinancialStatement.status == StatementStatus.DRAFT,
            LineItem.confidence < threshold,
        )
    )
    if body.company_id:
        base = base.where(FinancialStatement.company_id == body.company_id)
    if body.filing_id:
        base = base.join(Filing, FinancialStatement.filing_id == Filing.id)\
                   .where(Filing.id == body.filing_id)

    items: list[LineItem] = list((await db.execute(base)).scalars().all())

    if body.action == "approve_all":
        for item in items:
            item.confidence = 1.0
            item.approved_by = "bulk"
        result.approved = len(items)

    elif body.action == "reject_unmapped":
        to_delete = [i for i in items if i.canonical_key.startswith("unmapped:")]
        for item in to_delete:
            await db.delete(item)
        result.rejected = len(to_delete)
        # Keep the rest — don't touch them.
        items = [i for i in items if not i.canonical_key.startswith("unmapped:")]

    elif body.action == "approve_above":
        to_approve = [i for i in items if i.confidence >= body.threshold]
        for item in to_approve:
            item.confidence = 1.0
            item.approved_by = "bulk"
        result.approved = len(to_approve)
        # Items below threshold are untouched — they still need manual review.
        items = to_approve

    await db.flush()

    # Collect the unique filing IDs affected and check if any can be resumed.
    affected_statement_ids = {i.statement_id for i in items}
    affected_filing_ids: set[uuid.UUID] = set()
    for stmt_id in affected_statement_ids:
        statement = await db.get(FinancialStatement, stmt_id)
        if statement is None:
            continue
        remaining = await _remaining_low_conf(db, stmt_id)
        if remaining == 0:
            statement.status = StatementStatus.APPROVED
            affected_filing_ids.add(statement.filing_id)

    await db.commit()

    for filing_id in affected_filing_ids:
        await _continue_job_if_clear(db, filing_id)
        result.filings_resumed.append(str(filing_id))
        logger.info("bulk_review_filing_resumed", filing_id=str(filing_id))

    logger.info("bulk_review_done", action=body.action,
                approved=result.approved, rejected=result.rejected,
                filings_resumed=len(result.filings_resumed))
    return result


@router.get("/stats")
async def review_stats(db: AsyncSession = Depends(get_db),
                       company_id: uuid.UUID | None = None) -> dict:
    """Summary counts for the review queue — drives the bulk action UI."""
    from sqlalchemy import case, func

    threshold = get_settings().confidence_review_threshold
    base = (
        select(
            func.count().label("total"),
            func.sum(case((LineItem.canonical_key.like("unmapped:%"), 1), else_=0)).label("unmapped"),
            func.sum(case((LineItem.confidence >= 0.7, 1), else_=0)).label("high_conf"),
        )
        .join(FinancialStatement, LineItem.statement_id == FinancialStatement.id)
        .where(
            FinancialStatement.status == StatementStatus.DRAFT,
            LineItem.confidence < threshold,
        )
    )
    if company_id:
        base = base.where(FinancialStatement.company_id == company_id)
    row = (await db.execute(base)).one()
    return {
        "total": row.total or 0,
        "unmapped": int(row.unmapped or 0),
        "high_confidence": int(row.high_conf or 0),
        "manual_required": (row.total or 0) - int(row.unmapped or 0) - int(row.high_conf or 0),
    }
