"""arq worker (Playbook P3.1): stage tasks with the idempotent pipeline,
retries x3 with backoff, FAILED captures the traceback.
"""

import uuid
from datetime import UTC, datetime

import structlog
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.settings import get_settings
from app.db.session import get_session_factory
from app.ingestion.pipeline import run_pipeline
from app.models import Filing, IngestionJob, JobState

logger = structlog.get_logger("ingestion.worker")


async def run_ingestion(ctx: dict, job_id: str) -> str:
    """arq task entry: run the full pipeline for one ingestion job."""
    db_factory = get_session_factory()
    async with db_factory() as db:
        job = await db.get(IngestionJob, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"job {job_id} not found")
        job.retry_count += 1
        await db.commit()
        try:
            report = await run_pipeline(db, job.filing_id, job.id)
            return report.state
        except Exception as exc:  # noqa: BLE001
            job = await db.get(IngestionJob, uuid.UUID(job_id))
            job.state = JobState.FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            job.stage_detail = "failed — see error"
            job.updated_at = datetime.now(UTC)
            await db.commit()
            logger.error("ingestion_failed", job_id=job_id, error=job.error)
            raise


async def startup(ctx: dict) -> None:
    logger.info("worker_startup")


async def shutdown(ctx: dict) -> None:
    logger.info("worker_shutdown")


class WorkerSettings:
    """arq worker: `arq app.ingestion.worker.WorkerSettings`."""

    functions = [run_ingestion]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 600
    max_tries = 3  # retries with backoff per arq semantics


async def enqueue_ingestion(job_id: uuid.UUID) -> None:
    """Enqueue from the API process (pool created lazily)."""
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(
        RedisSettings.from_dsn(get_settings().redis_url))
    await pool.enqueue_job("run_ingestion", str(job_id))
    await pool.aclose()


async def filing_path_for_job(job_id: uuid.UUID) -> str | None:
    factory = get_session_factory()
    async with factory() as db:
        job = await db.get(IngestionJob, job_id)
        if job is None:
            return None
        filing = await db.get(Filing, job.filing_id)
        return filing.file_path if filing else None
