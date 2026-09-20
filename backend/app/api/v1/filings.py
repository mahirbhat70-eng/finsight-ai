"""Filings: upload (magic bytes + size), job status + SSE, file serving.

POST /api/v1/companies/{id}/filings (multipart) -> job id
GET  /api/v1/jobs/{id}                       -> state/progress/error
GET  /api/v1/jobs/{id}/events                -> SSE progress stream
GET  /api/v1/filings/{id}/file               -> source PDF (for the viewer)
"""

import asyncio
import time
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import get_request_id
from app.db.session import get_db
from app.models import Company, Filing, FilingDocType, IngestionJob, JobState
from app.ingestion.pipeline import job_state

router = APIRouter(tags=["filings"])
logger = structlog.get_logger("api.filings")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAGIC = {b"%PDF-": "pdf", b"PK\x03\x04": "xlsx"}
DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "uploads"


@router.post("/companies/{company_id}/filings", status_code=201)
async def upload_filing(company_id: uuid.UUID, file: UploadFile,
                        doc_type: str = "annual_report",
                        db: AsyncSession = Depends(get_db)) -> dict:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")

    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in ("pdf", "xlsx"):
        raise AppError("bad_extension", "only pdf and xlsx are accepted", 422)

    head = await file.read(8)
    await file.seek(0)
    kind = next((k for magic, k in MAGIC.items() if head.startswith(magic)), None)
    if kind != ext:
        raise AppError("bad_magic_bytes",
                       f"file content does not look like a .{ext}", 422)

    size = 0
    dest_dir = DATA_ROOT / str(company_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}.{ext}"
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise AppError("too_large", "file exceeds 50MB limit", 413)
            out.write(chunk)

    filing = Filing(company_id=company_id,
                    doc_type=FilingDocType.XLSX if ext == "xlsx"
                    else FilingDocType(doc_type),
                    file_path=str(dest), status="pending")
    db.add(filing)
    await db.flush()
    job = IngestionJob(filing_id=filing.id, state=JobState.PENDING,
                       stage_detail="queued")
    db.add(job)
    await db.commit()

    try:
        from app.ingestion.worker import enqueue_ingestion
        await enqueue_ingestion(job.id)
    except Exception as exc:  # noqa: BLE001 — queue down: run inline in dev
        logger.warning("enqueue_failed_running_inline", error=repr(exc))
        from app.ingestion.pipeline import run_pipeline
        await run_pipeline(db, filing.id, job.id, llm_assist=False)

    logger.info("filing_uploaded", filing_id=str(filing.id),
                company_id=str(company_id), size=size, request_id=get_request_id())
    return {"filing_id": str(filing.id), "job_id": str(job.id),
            "state": job.state.value if hasattr(job.state, "value") else job.state}


@router.get("/companies/{company_id}/filings")
async def list_filings(company_id: uuid.UUID,
                       db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(
        select(Filing).where(Filing.company_id == company_id)
    )).scalars().all()
    return [{"id": str(f.id), "doc_type": f.doc_type.value
             if hasattr(f.doc_type, "value") else str(f.doc_type),
             "file_path": f.file_path, "status": f.status,
             "num_pages": f.num_pages} for f in rows]


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID,
                  db: AsyncSession = Depends(get_db)) -> dict:
    return await job_state(db, job_id)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: uuid.UUID,
                     db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """SSE: state/progress on change + heartbeat. Closes on READY/FAILED."""

    async def event_stream():
        last_payload: dict = {}
        deadline = time.monotonic() + 900  # 15 min cap
        while time.monotonic() < deadline:
            try:
                payload = await job_state(db, job_id)
            except ValueError:
                yield "event: error\ndata: {\"error\": \"job not found\"}\n\n"
                return
            if payload != last_payload:
                import json

                last_payload = payload
                yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
                if payload["state"] in ("ready", "failed"):
                    yield "event: done\ndata: {}\n\n"
                    return
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.7)

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/filings/{filing_id}/file")
async def get_filing_file(filing_id: uuid.UUID,
                          db: AsyncSession = Depends(get_db)) -> FileResponse:
    filing = await db.get(Filing, filing_id)
    if filing is None:
        raise HTTPException(404, "filing not found")
    path = Path(filing.file_path)
    if not path.exists():
        raise HTTPException(404, "file missing on disk")
    media = "application/pdf" if path.suffix == ".pdf" else \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, media_type=media, filename=path.name)
