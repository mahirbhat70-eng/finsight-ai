"""Export jobs + download center (Playbook P6.5):
POST /api/v1/exports/{kind}   kind: xlsx | memo_pdf | pptx
GET  /api/v1/exports          list artifacts
GET  /api/v1/exports/{id}/download
"""

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_request_id
from app.db.session import get_db
from app.exports.charts import build_all
from app.exports.excel_model import build_workbook, save_workbook
from app.finmod.dcf import Forecast
from app.finmod.engine import run_company
from app.finmod.wacc import AssumptionSet
from app.models import Company, ExportArtifact
from app.services.series import load_company_series

router = APIRouter(prefix="/exports", tags=["exports"])
logger = structlog.get_logger("api.exports")

DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "exports"
KINDS = {"xlsx", "memo_pdf", "pptx"}


async def _generate(db: AsyncSession, company_id: uuid.UUID, kind: str,
                    assumptions: AssumptionSet, forecast: Forecast) -> Path:
    company = await db.get(Company, company_id)
    series, periods = await load_company_series(db, company_id)
    if not series:
        raise HTTPException(404, "no approved statements for this company")
    report = run_company(series, periods, assumptions, forecast)  # type: ignore[arg-type]
    out_dir = DATA_ROOT / str(company_id) / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{uuid.uuid4().hex}.{kind.split('_')[-1]}"

    if kind == "xlsx":
        wb = build_workbook(series, periods, assumptions, forecast,  # type: ignore[arg-type]
                            company_name=company.name if company else "company",
                            assumptions_version="api-1")
        wb.save(path)
    elif kind == "memo_pdf":
        from app.exports.memo_pdf import build_memo

        charts = build_all(periods, series, report, out_dir)
        build_memo(str(path), report, series, periods,
                   company.name if company else "company", chart_paths=charts)
    elif kind == "pptx":
        from app.exports.deck import build_deck

        charts = build_all(periods, series, report, out_dir)
        build_deck(str(path), report, series, periods,
                   company.name if company else "company", chart_paths=charts)
    return path


@router.post("/{kind}", status_code=201)
async def create_export(kind: str, company_id: uuid.UUID,
                        assumptions: AssumptionSet | None = None,
                        forecast: Forecast | None = None,
                        db: AsyncSession = Depends(get_db)) -> dict:
    if kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {sorted(KINDS)}")
    path = await _generate(db, company_id, kind,
                           assumptions or AssumptionSet(),
                           forecast or Forecast())
    artifact = ExportArtifact(company_id=company_id, kind=kind,
                              file_path=str(path), assumptions_version="api-1")
    db.add(artifact)
    await db.commit()
    logger.info("export_created", kind=kind, company_id=str(company_id),
                request_id=get_request_id())
    return {"artifact_id": str(artifact.id), "kind": kind,
            "download_url": f"/api/v1/exports/{artifact.id}/download"}


@router.get("")
async def list_exports(company_id: uuid.UUID | None = None,
                       db: AsyncSession = Depends(get_db)) -> list[dict]:
    stmt = select(ExportArtifact).order_by(ExportArtifact.created_at.desc())
    if company_id:
        stmt = stmt.where(ExportArtifact.company_id == company_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": str(a.id), "company_id": str(a.company_id), "kind": a.kind,
             "created_at": a.created_at.isoformat()} for a in rows]


@router.get("/{artifact_id}/download")
async def download(artifact_id: uuid.UUID,
                   db: AsyncSession = Depends(get_db)) -> FileResponse:
    artifact = await db.get(ExportArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "artifact not found")
    path = Path(artifact.file_path)
    if not path.exists():
        raise HTTPException(404, "artifact file missing on disk")
    media = {"xlsx": "application/vnd.openxmlformats-officedocument"
                     ".spreadsheetml.sheet",
             "memo_pdf": "application/pdf",
             "pptx": "application/vnd.openxmlformats-officedocument"
                     ".presentationml.presentation"}[artifact.kind]
    return FileResponse(path, media_type=media, filename=path.name)
