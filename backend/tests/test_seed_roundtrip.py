"""Golden test: seed -> read back -> equals fixtures JSON (Playbook P1.5).

Integration test — needs Postgres (docker compose up -d).
Run: pytest tests/test_seed_roundtrip.py -m integration
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import Company, FinancialStatement, LineItem, StatementStatus
from novatech_model import build_model

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
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


async def test_seed_roundtrip() -> None:
    import asyncio

    from seed import seed

    await seed()

    expected = json.loads((FIXTURES / "novatech_statements.json").read_text())
    factory = get_session_factory()
    async with factory() as session:
        company = (await session.execute(
            select(Company).where(Company.name == "NovaTech Industries Ltd"))
        ).scalar_one()

        stmts = (await session.execute(
            select(FinancialStatement)
            .where(FinancialStatement.company_id == company.id))
        ).scalars().all()
        approved = [s for s in stmts if s.status == StatementStatus.APPROVED]
        assert len(approved) == 15  # 5 periods x 3 statements

        by_key_period: dict[tuple[str, str], float] = {}
        for stmt in approved:
            items = (await session.execute(
                select(LineItem)
                .where(LineItem.statement_id == stmt.id))
            ).scalars().all()
            for it in items:
                by_key_period[(it.canonical_key, stmt.period)] = float(it.value)

        model = build_model()
        mismatches = 0
        for key, values in expected["items"].items():
            for period, value in zip(expected["periods"], values):
                got = by_key_period.get((key, period))
                assert got is not None, f"missing {key} {period}"
                if abs(got - value) > 0.02:
                    mismatches += 1
        assert mismatches == 0, f"{mismatches} seeded values differ from fixtures"
