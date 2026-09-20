"""Companies: list + create (workspace entities)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.models import Company
from app.schemas.api import CompanyIn

router = APIRouter(prefix="/companies", tags=["companies"])
logger = get_logger("api.companies")


@router.get("")
async def list_companies(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(select(Company).order_by(Company.created_at))).scalars()
    return [{"id": str(c.id), "name": c.name, "sector": c.sector,
             "currency": c.currency, "fiscal_year_end": c.fiscal_year_end}
            for c in rows]


@router.post("", status_code=201)
async def create_company(payload: CompanyIn,
                         db: AsyncSession = Depends(get_db)) -> dict:
    company = Company(**payload.model_dump())
    db.add(company)
    await db.commit()
    logger.info("company_created", company_id=str(company.id), name=company.name)
    return {"id": str(company.id), "name": company.name}


@router.get("/{company_id}")
async def get_company(company_id: uuid.UUID,
                      db: AsyncSession = Depends(get_db)) -> dict:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    return {"id": str(company.id), "name": company.name, "sector": company.sector,
            "currency": company.currency, "fiscal_year_end": company.fiscal_year_end}
