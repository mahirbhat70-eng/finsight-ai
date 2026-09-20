"""POST /companies/{id}/valuation — run the deterministic DCF, persist the run
(never recomputed silently: every run is stored)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.session import get_db
from app.finmod.engine import run_company
from app.models import AssumptionSet, Company, DcfRun
from app.schemas.api import ValuationRequest
from app.services.series import load_company_series, require_latest

router = APIRouter(prefix="/companies", tags=["valuation"])
logger = get_logger("api.valuation")


@router.post("/{company_id}/valuation")
async def run_valuation(company_id: uuid.UUID, payload: ValuationRequest,
                        db: AsyncSession = Depends(get_db)) -> dict:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")

    series, periods = await load_company_series(db, company_id)
    if not series:
        raise HTTPException(404, "no approved statements for this company")
    require_latest(series, ("revenue", "ebitda", "total_debt", "cash",
                            "total_equity", "shares_outstanding"))

    try:
        report = run_company(series, periods, payload.assumptions,  # type: ignore[arg-type]
                             payload.forecast)
    except ValueError as exc:
        raise AppError("valuation_input_error", str(exc), status_code=422) from exc

    if payload.persist:
        assumption_set = AssumptionSet(
            company_id=company_id, name="api",
            payload={"assumptions": payload.assumptions.model_dump(),
                     "forecast": payload.forecast.model_dump()},
            version=1)
        db.add(assumption_set)
        await db.flush()
        db.add(DcfRun(
            assumption_set_id=assumption_set.id, company_id=company_id,
            result={"bridge": report["dcf"]["bridge"],
                    "wacc": report["wacc"],
                    "scenarios": report["scenarios"]},
            checks=report["dcf"]["checks"]))
        await db.commit()
        logger.info("valuation_run", company_id=str(company_id),
                    per_share=report["dcf"]["bridge"]["per_share_inr"])

    report["company_id"] = str(company_id)
    return report
