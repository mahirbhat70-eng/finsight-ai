import asyncio
import uuid
from app.db.session import get_session_factory
from app.models import IngestionJob, Filing, Chunk
from app.ingestion.pipeline import continue_after_review
from sqlalchemy import select, func

async def test_embed():
    async with get_session_factory()() as db:
        jobs = (await db.execute(select(IngestionJob).order_by(IngestionJob.created_at.desc()))).scalars().all()
        target_job = jobs[0]
        print(f"Target job: {target_job.id}, filing_id: {target_job.filing_id}, state: {target_job.state}")
        
        try:
            print("Calling continue_after_review directly...")
            cnt = await continue_after_review(db, target_job.filing_id, target_job.id)
            print(f"Success! Indexed {cnt} chunks.")
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_embed())
