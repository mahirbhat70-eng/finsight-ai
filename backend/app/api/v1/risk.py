"""GET /companies/{id}/risk — rule-engine flags by category + composite score."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.finmod.ratios import compute_metrics
from app.finmod.risk_rules import RuleEngine
from app.finmod.wacc import AssumptionSet, compute_wacc
from app.models import Company, PeerMetric, RiskAssessment
from app.services.series import load_company_series

router = APIRouter(prefix="/companies", tags=["risk"])


@router.get("/{company_id}/risk")
async def get_risk(company_id: uuid.UUID,
                   top_customer_concentration: float | None = None,
                   db: AsyncSession = Depends(get_db)) -> dict:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")

    series, periods = await load_company_series(db, company_id)
    if not series:
        raise HTTPException(404, "no approved statements for this company")

    # Concentration: explicit query param wins, else peer_metrics store.
    if top_customer_concentration is None:
        row = (await db.execute(
            select(PeerMetric.value).where(
                PeerMetric.metric_key == "top_customer_concentration")
        )).scalar_one_or_none()  # demo fixture: single global value
        if row is not None:
            top_customer_concentration = row

    metrics = compute_metrics(series, periods)  # type: ignore[arg-type]
    wacc, _ = compute_wacc(AssumptionSet(), series, periods)  # type: ignore[arg-type]
    fcf_series = [(p, v) for p, v in zip(periods, series.get("fcf", []))
                  if v is not None]
    ebitda_series = [v for v in series.get("ebitda", []) if v is not None]
    context = {"wacc": wacc, "fcf_series": fcf_series,
               "ebitda_series": ebitda_series,
               "top_customer_concentration": top_customer_concentration}

    assessment = RuleEngine().assess(metrics, periods, context)
    db.add(RiskAssessment(company_id=company_id, flags=assessment["flags"],
                          composite_score=assessment["composite_score"]))
    await db.commit()
    return {"company_id": str(company_id), **assessment}
