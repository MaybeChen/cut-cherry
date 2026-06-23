from pathlib import Path
def job_artifact(job_dir: Path, name: str) -> Path:
    return job_dir / name
