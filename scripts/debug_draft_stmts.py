import asyncio
from app.db.session import get_session_factory
from app.models import Chunk, Filing, IngestionJob, FinancialStatement, StatementStatus, LineItem
from sqlalchemy import select, func

async def check():
    async with get_session_factory()() as db:
        chunks_count = (await db.execute(select(func.count(Chunk.id)))).scalar()
        print('Total chunks in DB:', chunks_count)
        
        filings = (await db.execute(select(Filing))).scalars().all()
        for f in filings:
            print(f"Filing {f.id}: doc_type={f.doc_type} status={f.status} num_pages={f.num_pages}")
            
        jobs = (await db.execute(select(IngestionJob))).scalars().all()
        for j in jobs:
            print(f"Job {j.id}: filing_id={j.filing_id} state={j.state} progress={j.progress} stage_detail={j.stage_detail} error={j.error}")
            
        stmts = (await db.execute(select(FinancialStatement))).scalars().all()
        print(f"Total statements: {len(stmts)}")
        draft_stmts = [s for s in stmts if s.status == StatementStatus.DRAFT]
        print(f"Draft statements: {len(draft_stmts)}")
        for s in draft_stmts:
            items = (await db.execute(select(LineItem).where(LineItem.statement_id == s.id))).scalars().all()
            low = [i for i in items if i.confidence < 0.85]
            print(f"  Draft stmt {s.id}: filing={s.filing_id} period={s.period} type={s.statement_type} total_items={len(items)} low_conf={len(low)}")

if __name__ == '__main__':
    asyncio.run(check())
