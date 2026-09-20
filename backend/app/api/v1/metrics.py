"""Canonical series + ratio metrics with lineage (approved statements only)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.finmod.ratios import compute_metrics
from app.models import Company
from app.services.series import load_company_series

router = APIRouter(prefix="/companies", tags=["metrics"])
logger = get_logger("api.metrics")


async def _company_or_404(db: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    return company


@router.get("/{company_id}/metrics")
async def get_metrics(company_id: uuid.UUID,
                      db: AsyncSession = Depends(get_db)) -> dict:
    await _company_or_404(db, company_id)
    series, periods = await load_company_series(db, company_id)
    if not series:
        raise HTTPException(404, "no approved statements for this company")
    table = compute_metrics(series, periods)  # type: ignore[arg-type]
    return {
        "company_id": str(company_id),
        "periods": periods,
        "series": series,
        "metrics": table.to_json(),
    }
