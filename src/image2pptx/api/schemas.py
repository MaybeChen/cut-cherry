from __future__ import annotations
from pydantic import BaseModel

class JobResponse(BaseModel):
    job_id: str
    status: str
    pptx_path: str | None = None
    ir_path: str | None = None
