from __future__ import annotations
from dataclasses import dataclass

@dataclass
class JobRecord:
    job_id: str
    status: str
    pptx_path: str | None = None
    ir_path: str | None = None

class InMemoryJobStore:
    def __init__(self) -> None: self.jobs: dict[str, JobRecord] = {}
    def put(self, record: JobRecord) -> None: self.jobs[record.job_id]=record
    def get(self, job_id: str) -> JobRecord | None: return self.jobs.get(job_id)
STORE=InMemoryJobStore()
