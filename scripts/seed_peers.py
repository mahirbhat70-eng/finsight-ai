"""Seed the 3-peer benchmark fixture (Playbook P6.1) + top-customer context.

make seed-peers
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import delete, select

from app.db.session import get_session_factory, init_models
from app.models import Company, Peer, PeerMetric

PEERS = [
    {  # margins per the original concept table: 19.8 / 25.4 / 17.6
        "name": "Kaveri Precision Engineering Ltd",
        "metrics": {"revenue_growth": 13.2, "ebitda_margin": 25.4, "roe": 21.8,
                    "debt_to_equity": 0.4, "fcf_margin": 6.2, "interest_cover": 8.4,
                    "roic": 16.1, "ev_ebitda": 14.2},
    },
    {
        "name": "Orbit Systems Ltd",
        "metrics": {"revenue_growth": 9.4, "ebitda_margin": 19.8, "roe": 15.2,
                    "debt_to_equity": 0.7, "fcf_margin": 4.1, "interest_cover": 5.6,
                    "roic": 12.4, "ev_ebitda": 11.5},
    },
    {
        "name": "Deccan Assemblies Pvt Ltd",
        "metrics": {"revenue_growth": 6.8, "ebitda_margin": 17.6, "roe": 11.9,
                    "debt_to_equity": 0.9, "fcf_margin": 2.8, "interest_cover": 4.2,
                    "roic": 9.7, "ev_ebitda": 9.8},
    },
]

# Sourced from the NovaTech ground truth (Note 2 — customer concentration).
CONTEXT_METRICS = {"top_customer_concentration": 14.2}


async def seed_peers() -> None:
    await init_models()
    factory = get_session_factory()
    async with factory() as db:
        company = (await db.execute(
            select(Company).where(Company.name == "NovaTech Industries Ltd"))
        ).scalars().first()
        if company is None:
            print("NovaTech not found — run `make seed` first")
            return

        await db.execute(delete(PeerMetric).where(
            PeerMetric.peer_id.in_(select(Peer.id).where(Peer.company_id == company.id))))
        await db.execute(delete(Peer).where(Peer.company_id == company.id))

        for spec in PEERS:
            peer = Peer(company_id=company.id, name=spec["name"],
                        sector="Industrial Automation")
            db.add(peer)
            await db.flush()
            for key, value in spec["metrics"].items():
                db.add(PeerMetric(peer_id=peer.id, metric_key=key, value=value,
                                  period="FY2025", source="seed fixture"))
        # global context row (risk engine reads it via peer_metrics)
        from sqlalchemy import func

        existing = (await db.execute(
            select(func.count()).select_from(PeerMetric)
            .where(PeerMetric.metric_key == "top_customer_concentration")
        )).scalar_one()
        if not existing:
            ghost = Peer(company_id=company.id, name="__context__", sector="context")
            db.add(ghost)
            await db.flush()
            db.add(PeerMetric(peer_id=ghost.id,
                              metric_key="top_customer_concentration",
                              value=CONTEXT_METRICS["top_customer_concentration"],
                              period="FY2025", source="novatech ground truth"))
        await db.commit()
        print(f"seeded {len(PEERS)} peers for NovaTech + concentration context")


if __name__ == "__main__":
    asyncio.run(seed_peers())
