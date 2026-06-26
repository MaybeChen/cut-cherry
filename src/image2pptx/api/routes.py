from __future__ import annotations
from pathlib import Path
import shutil
import tempfile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from image2pptx.api.dependencies import get_settings
from image2pptx.api.schemas import JobResponse
from image2pptx.config.settings import Settings
from image2pptx.pipeline.orchestrator import ImageToPptxPipeline
from image2pptx.storage.job_store import STORE, JobRecord

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/jobs", response_model=JobResponse)
def create_job(
    file: UploadFile = File(...), settings: Settings = Depends(get_settings)
) -> JobResponse:
    suffix = Path(file.filename or "input.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".pdf"}:
        raise HTTPException(400, "unsupported file type")
    tmp = Path(tempfile.mkdtemp()) / ("input" + suffix)
    with tmp.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = ImageToPptxPipeline(settings).run(tmp)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    STORE.put(JobRecord(result.job_id, "completed", str(result.pptx_path), str(result.ir_path)))
    return JobResponse(
        job_id=result.job_id,
        status="completed",
        pptx_path=str(result.pptx_path),
        ir_path=str(result.ir_path),
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    rec = STORE.get(job_id)
    if not rec:
        raise HTTPException(404, "job not found")
    return JobResponse(
        job_id=rec.job_id, status=rec.status, pptx_path=rec.pptx_path, ir_path=rec.ir_path
    )


@router.get("/jobs/{job_id}/artifacts")
def artifacts(job_id: str) -> dict[str, str | None]:
    rec = STORE.get(job_id)
    if not rec:
        raise HTTPException(404, "job not found")
    return {"pptx": rec.pptx_path, "slide_ir": rec.ir_path}


@router.get("/jobs/{job_id}/download/pptx")
def download(job_id: str):
    rec = STORE.get(job_id)
    if not rec or not rec.pptx_path:
        raise HTTPException(404, "pptx not found")
    return FileResponse(rec.pptx_path, filename="result.pptx")
