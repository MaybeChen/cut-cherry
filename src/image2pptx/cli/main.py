from __future__ import annotations
from pathlib import Path
import typer
from rich import print
from image2pptx.config.settings import load_settings
from image2pptx.pipeline.orchestrator import ImageToPptxPipeline

app = typer.Typer(help="Image/PDF page to editable PPTX service")

@app.command()
def convert(input_path: Path, config: Path | None = None, device: str | None = None, no_sam3: bool = False, no_vlm: bool = False, no_refine: bool = False) -> None:
    settings=load_settings(config, device)
    if no_sam3: settings.pipeline.enable_sam3=False
    if no_vlm: settings.pipeline.enable_vlm=False
    if no_refine: settings.pipeline.enable_refinement=False
    result=ImageToPptxPipeline(settings).run(input_path)
    print({"job_id": result.job_id, "pptx": str(result.pptx_path), "slide_ir": str(result.ir_path)})

@app.command()
def inspect(input_path: Path, config: Path | None = None, device: str | None = "cpu") -> None:
    settings=load_settings(config, device); result=ImageToPptxPipeline(settings).run(input_path)
    print(Path(result.ir_path).read_text(encoding="utf-8"))

@app.command()
def render(pptx_path: Path) -> None:
    print(f"PPTX render preview is implemented via LibreOffice adapter in Phase 4: {pptx_path}")

@app.command()
def evaluate(source: Path, preview: Path) -> None:
    from image2pptx.evaluation.metrics import compute_basic_metrics
    print(compute_basic_metrics(source, preview))
