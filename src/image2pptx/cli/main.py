from __future__ import annotations
from pathlib import Path
import json
import typer
from rich import print
from image2pptx.config.settings import load_settings
from image2pptx.pipeline.orchestrator import ImageToPptxPipeline

app = typer.Typer(help="Image/PDF page to editable PPTX service")


@app.command()
def convert(
    input_path: Path,
    config: Path | None = None,
    device: str | None = None,
    no_sam3: bool = False,
    no_vlm: bool = False,
    no_refine: bool = False,
) -> None:
    settings = load_settings(config, device)
    if no_sam3:
        settings.pipeline.enable_sam3 = False
    if no_vlm:
        settings.pipeline.enable_vlm = False
    if no_refine:
        settings.pipeline.enable_refinement = False
    result = ImageToPptxPipeline(settings).run(input_path)
    print({"job_id": result.job_id, "pptx": str(result.pptx_path), "slide_ir": str(result.ir_path)})
    _print_ocr_report(result.job_dir / "ocr_results.json")


@app.command()
def inspect(input_path: Path, config: Path | None = None, device: str | None = "cpu") -> None:
    settings = load_settings(config, device)
    result = ImageToPptxPipeline(settings).run(input_path)
    print(Path(result.ir_path).read_text(encoding="utf-8"))


@app.command()
def render(pptx_path: Path) -> None:
    print(f"PPTX render preview is implemented via LibreOffice adapter in Phase 4: {pptx_path}")


@app.command()
def evaluate(source: Path, preview: Path) -> None:
    from image2pptx.evaluation.metrics import compute_basic_metrics

    print(compute_basic_metrics(source, preview))


def _print_ocr_report(report_path: Path) -> None:
    if not report_path.exists():
        print({"ocr_status": "not_run", "message": "OCR report was not generated."})
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    items = report.get("items", [])
    summary = {
        "ocr_status": report.get("status"),
        "ocr_count": report.get("count", len(items)),
        "ocr_report": str(report_path),
    }
    if report.get("warnings"):
        summary["ocr_warnings"] = report["warnings"]
    print(summary)
    if items:
        print("OCR recognized text:")
        for item in items[:100]:
            print(
                {
                    "text": item.get("text"),
                    "confidence": item.get("confidence"),
                    "bbox": item.get("bbox"),
                }
            )
        if len(items) > 100:
            print(
                {
                    "ocr_truncated": len(items) - 100,
                    "message": "Open ocr_results.json for all OCR items.",
                }
            )
