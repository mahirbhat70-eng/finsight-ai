import asyncio
from app.db.session import get_session_factory
from app.models import Chunk, Filing, IngestionJob, FinancialStatement, StatementStatus
from sqlalchemy import select, func

async def check():
    async with get_session_factory()() as db:
        chunks_count = (await db.execute(select(func.count(Chunk.id)))).scalar()
        filings = (await db.execute(select(Filing))).scalars().all()
        jobs = (await db.execute(select(IngestionJob))).scalars().all()
        stmts = (await db.execute(select(FinancialStatement))).scalars().all()
        print('Total chunks in DB:', chunks_count)
        print('Total filings:', len(filings))
        print('Statements count:', len(stmts))
        drafts = [s for s in stmts if s.status == StatementStatus.DRAFT]
        approved = [s for s in stmts if s.status == StatementStatus.APPROVED]
        print(f'Draft stmts: {len(drafts)}, Approved stmts: {len(approved)}')
        for j in jobs:
            print(f'Job {j.id}: state={j.state}, progress={j.progress}, detail={j.detail}')

if __name__ == '__main__':
    asyncio.run(check())
