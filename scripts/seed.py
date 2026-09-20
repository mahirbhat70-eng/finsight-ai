"""Seed the database from the NovaTech fixtures (Playbook P1.5).

Wipes prior NovaTech rows, inserts company, two filings (pdf + xlsx), one
approved statement set per period x {pl, bs, cf} attached to the PDF filing,
and line items with confidence=1.0 + page_no from the ground truth.

Run: cd backend && python ../scripts/seed.py   (or: make seed)
"""

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import delete, func, select

from app.db.session import get_session_factory, init_models
from app.models import (
    Company,
    Filing,
    FilingDocType,
    FinancialStatement,
    LineItem,
    StatementStatus,
    StatementType,
)

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"
COMPANY_NAME = "NovaTech Industries Ltd"

STMT_FOR_ITEM = {
    "revenue": "pl", "cogs": "pl", "gross_profit": "pl", "opex": "pl",
    "ebitda": "pl", "dna": "pl", "ebit": "pl", "interest_expense": "pl",
    "other_income": "pl", "pbt": "pl", "tax_expense": "pl", "pat": "pl",
    "shares_outstanding": "pl",
    "cash": "bs", "trade_receivables": "bs", "inventory": "bs",
    "current_assets": "bs", "trade_payables": "bs", "current_liabilities": "bs",
    "st_borrowings": "bs", "lt_debt": "bs", "total_debt": "bs",
    "total_equity": "bs",
    "ocf": "cf", "capex": "cf", "fcf": "cf",
}


async def seed() -> None:
    await init_models()  # create_all if tables absent (dev path; prod uses Alembic)

    statements = json.loads((FIXTURES / "novatech_statements.json").read_text())
    ground_truth = json.loads((FIXTURES / "novatech_ground_truth.json").read_text())
    page_for = {(f["key"], f["period"]): f["page_no"] for f in ground_truth["facts"]}

    factory = get_session_factory()
    async with factory() as session:
        # Idempotent: wipe prior NovaTech company (cascades everything).
        result = await session.execute(
            select(Company).where(Company.name == COMPANY_NAME))
        for company in result.scalars():
            await session.delete(company)

        company = Company(name=COMPANY_NAME, sector="Industrial Automation",
                          currency="INR", fiscal_year_end="March")
        session.add(company)
        await session.flush()

        pdf_filing = Filing(
            company_id=company.id, doc_type=FilingDocType.ANNUAL_REPORT,
            file_path=str(FIXTURES / "novatech_annual_report.pdf"),
            status="ready", num_pages=ground_truth["pages"]["num_pages"])
        xlsx_filing = Filing(
            company_id=company.id, doc_type=FilingDocType.XLSX,
            file_path=str(FIXTURES / "novatech.xlsx"), status="ready")
        session.add_all([pdf_filing, xlsx_filing])
        await session.flush()

        stmt_ids: dict[tuple[str, str], FinancialStatement] = {}
        for period in statements["periods"]:
            for stype in ("pl", "bs", "cf"):
                stmt = FinancialStatement(
                    filing_id=pdf_filing.id, company_id=company.id,
                    period=period, statement_type=StatementType(stype),
                    status=StatementStatus.APPROVED)
                session.add(stmt)
                stmt_ids[(period, stype)] = stmt
        await session.flush()

        count = 0
        for key, values in statements["items"].items():
            stype = STMT_FOR_ITEM[key]
            for period, value in zip(statements["periods"], values):
                item = LineItem(
                    statement_id=stmt_ids[(period, stype)].id,
                    canonical_key=key,
                    value=Decimal(str(round(value, 2))),
                    unit="mn_shares" if key == "shares_outstanding" else "INR_cr",
                    page_no=page_for.get((key, period)),
                    raw_label="", confidence=1.0, method="seed",
                    source="fixture", approved_by="seed")
                session.add(item)
                count += 1
        await session.commit()

        n_items = await session.scalar(
            select(func.count()).select_from(LineItem))
        n_stmts = await session.scalar(
            select(func.count()).select_from(FinancialStatement))
        print(f"seed complete: company={COMPANY_NAME} filings=2 "
              f"statements={n_stmts} line_items={n_items} (inserted {count})")
        assert n_items and n_items >= 130, "seed produced too few line items"


if __name__ == "__main__":
    asyncio.run(seed())
