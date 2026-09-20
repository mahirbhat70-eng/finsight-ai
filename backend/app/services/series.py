"""Load canonical series from APPROVED statements only (Playbook U3/U5).

Draft extractions live behind the review queue; the engine never sees them.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finmod.taxonomy import ALL_KEYS
from app.models import FinancialStatement, LineItem, StatementStatus


async def load_company_series(db: AsyncSession, company_id: uuid.UUID
                              ) -> tuple[dict[str, list[float | None]], list[str]]:
    stmt = (
        select(FinancialStatement.period, LineItem.canonical_key, LineItem.value)
        .join(LineItem, LineItem.statement_id == FinancialStatement.id)
        .where(FinancialStatement.company_id == company_id,
               FinancialStatement.status == StatementStatus.APPROVED,
               LineItem.canonical_key.in_(ALL_KEYS))
        .order_by(FinancialStatement.period)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return {}, []

    periods = sorted({r.period for r in rows})
    values = {(r.canonical_key, r.period): float(r.value) for r in rows}
    keys = {r.canonical_key for r in rows}
    series = {key: [values.get((key, p)) for p in periods] for key in sorted(keys)}
    return series, periods


def require_latest(series: dict[str, list[float | None]], keys: tuple[str, ...]
                   ) -> None:
    """Raise a clear error when a DCF-blocking input is missing."""
    missing = [k for k in keys if not series.get(k)]
    if missing:
        raise ValueError(f"missing canonical inputs for DCF: {missing}")
