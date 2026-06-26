from __future__ import annotations
import uuid
from pathlib import Path
from image2pptx.config.device import resolve_device
from image2pptx.config.settings import Settings
from image2pptx.pipeline.context import PipelineContext
from image2pptx.processors.preprocess import PreprocessProcessor
from image2pptx.processors.text_processor import TextProcessor
from image2pptx.processors.geometry_processor import GeometryProcessor
from image2pptx.processors.layout_parser import LayoutParserProcessor
from image2pptx.processors.sam3_processor import Sam3Processor
from image2pptx.processors.table_processor import TableProcessor
from image2pptx.processors.formula_processor import FormulaProcessor
from image2pptx.processors.chart_processor import ChartProcessor
from image2pptx.processors.arrow_processor import ArrowProcessor
from image2pptx.processors.candidate_fusion import CandidateFusionProcessor
from image2pptx.processors.layer_decomposition import LayerDecompositionProcessor
from image2pptx.processors.text_layer import TextLayerProcessor
from image2pptx.processors.vlm_arbitration import VlmArbitrationProcessor
from image2pptx.renderers.pptx_renderer import PptxRenderer


class PipelineResult:
    def __init__(self, job_id: str, job_dir: Path, pptx_path: Path, ir_path: Path) -> None:
        self.job_id = job_id
        self.job_dir = job_dir
        self.pptx_path = pptx_path
        self.ir_path = ir_path


class ImageToPptxPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self, input_path: Path) -> PipelineResult:
        device = resolve_device(self.settings.runtime.device)
        job_id = uuid.uuid4().hex[:12]
        job_dir = Path(self.settings.output.root_dir) / job_id
        _print_chain_header(job_id, input_path, job_dir, device)
        ctx = PipelineContext(
            job_id=job_id,
            input_path=input_path,
            job_dir=job_dir,
            settings=self.settings,
            device=device,
        )
        _run_stage(
            ctx,
            "preprocess",
            "规范化输入、生成灰度/边缘/颜色空间等中间产物",
            PreprocessProcessor().run,
        )
        if self.settings.pipeline.enable_geometry:
            _run_stage(ctx, "geometry", "OpenCV 轮廓/矩形/线段候选提取", GeometryProcessor().run)
            _run_stage(
                ctx,
                "arrow",
                "Hough 线段转基础 connector；箭头头部识别失败将直接报错",
                ArrowProcessor().run,
            )
        else:
            _print_stage_skipped("geometry+arrow", "settings.pipeline.enable_geometry=false")
        if self.settings.pipeline.enable_sam3:
            _run_stage(
                ctx,
                "sam3",
                "SAM3 endpoint/local runtime 视觉候选；失败时直接中断并打印原因",
                Sam3Processor().run,
            )
        else:
            _print_stage_skipped("sam3", "settings.pipeline.enable_sam3=false")
        if self.settings.pipeline.enable_text:
            _run_stage(ctx, "text", "OCR 文本识别；失败时直接中断并打印原因", TextProcessor().run)
        else:
            _print_stage_skipped("text", "settings.pipeline.enable_text=false")
        if self.settings.pipeline.enable_layout:
            _run_stage(
                ctx,
                "layout",
                "结构化 layout 模型 + 规则区域融合；模型失败时直接中断",
                LayoutParserProcessor().run,
            )
        else:
            _print_stage_skipped("layout", "settings.pipeline.enable_layout=false")
        if self.settings.pipeline.enable_text:
            _run_stage(
                ctx,
                "text_layer",
                "OCR 结果行/角色/样式归一化，形成可编辑 TextLayer",
                TextLayerProcessor().run,
            )
        else:
            _print_stage_skipped("text_layer", "settings.pipeline.enable_text=false")
        if self.settings.pipeline.enable_table:
            _run_stage(
                ctx,
                "table",
                "表格 cell/html 结构归一化；缺失结构时保留候选 bbox",
                TableProcessor().run,
            )
        else:
            _print_stage_skipped("table", "settings.pipeline.enable_table=false")
        if self.settings.pipeline.enable_formula:
            _run_stage(ctx, "formula", "公式样式 OCR 文本检测", FormulaProcessor().run)
        else:
            _print_stage_skipped("formula", "settings.pipeline.enable_formula=false")
        if self.settings.pipeline.enable_chart:
            _run_stage(ctx, "chart", "简单柱状图候选检测", ChartProcessor().run)
        else:
            _print_stage_skipped("chart", "settings.pipeline.enable_chart=false")
        _run_stage(
            ctx,
            "layer_decomposition",
            "按 background/container/text/asset/connector 显式分层并建立父子归属",
            LayerDecompositionProcessor().run,
        )
        if self.settings.pipeline.enable_vlm:
            _run_stage(
                ctx,
                "vlm_arbitration",
                "OpenAI 兼容 VLM 对分层候选做语义仲裁；失败时直接中断",
                VlmArbitrationProcessor().run,
            )
        else:
            _print_stage_skipped("vlm_arbitration", "settings.pipeline.enable_vlm=false")
        ir = _run_stage(
            ctx,
            "candidate_fusion",
            "融合 layout/text/table/image/formula/chart/connector 为 SlideIR，并生成图片资产",
            CandidateFusionProcessor().run,
        )
        ir_path = job_dir / "slide_ir.json"
        _run_stage(
            ctx,
            "slide_ir_export",
            f"写出 SlideIR JSON: {ir_path}",
            lambda _ctx: ir.export_json(ir_path),
        )
        pptx = _run_stage(
            ctx,
            "pptx_render",
            "python-pptx 渲染 result.pptx",
            lambda _ctx: PptxRenderer().render(ir, job_dir / "result.pptx"),
        )
        _print_chain_footer(job_id, pptx, ir_path)
        return PipelineResult(job_id, job_dir, pptx, ir_path)


def _print_separator() -> None:
    print("[image2pptx][chain] " + "=" * 88)


def _print_chain_header(job_id: str, input_path: Path, job_dir: Path, device: str) -> None:
    _print_separator()
    print(f"[image2pptx][chain] START job_id={job_id}")
    print(f"[image2pptx][chain] input={input_path}")
    print(f"[image2pptx][chain] output_dir={job_dir}")
    print(f"[image2pptx][chain] device={device}")
    _print_separator()


def _print_chain_footer(job_id: str, pptx_path: Path, ir_path: Path) -> None:
    _print_separator()
    print(f"[image2pptx][chain] DONE job_id={job_id}")
    print(f"[image2pptx][chain] pptx={pptx_path}")
    print(f"[image2pptx][chain] slide_ir={ir_path}")
    _print_separator()


def _print_stage_skipped(name: str, reason: str) -> None:
    _print_separator()
    print(f"[image2pptx][chain][{name}] SKIPPED")
    print(f"[image2pptx][chain][{name}] reason={reason}")


def _run_stage(ctx: PipelineContext, name: str, description: str, func):
    _print_separator()
    print(f"[image2pptx][chain][{name}] START")
    print(f"[image2pptx][chain][{name}] action={description}")
    before = _snapshot_ctx(ctx)
    try:
        result = func(ctx)
    except Exception as exc:
        print(f"[image2pptx][chain][{name}] FAILED error={type(exc).__name__}: {exc}")
        print(f"[image2pptx][chain][{name}] aborted=true")
        raise
    after = _snapshot_ctx(ctx)
    print(f"[image2pptx][chain][{name}] SUCCESS")
    for line in _summarize_delta(before, after):
        print(f"[image2pptx][chain][{name}] {line}")
    for line in _summarize_degradation(ctx, name):
        print(f"[image2pptx][chain][{name}] {line}")
    return result


def _snapshot_ctx(ctx: PipelineContext) -> dict[str, dict[str, int]]:
    artifacts = getattr(ctx, "artifacts", {}) or {}
    candidates = getattr(ctx, "candidates", {}) or {}
    return {
        "artifacts": {key: 1 for key in artifacts},
        "candidates": {key: _safe_len(value) for key, value in candidates.items()},
    }


def _safe_len(value) -> int:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1 if value is not None else 0


def _summarize_delta(
    before: dict[str, dict[str, int]], after: dict[str, dict[str, int]]
) -> list[str]:
    lines: list[str] = []
    for section in ("artifacts", "candidates"):
        added = sorted(set(after[section]) - set(before[section]))
        changed = sorted(
            key
            for key in set(after[section]) & set(before[section])
            if after[section][key] != before[section][key]
        )
        if added:
            lines.append(
                f"{section}_added={{{', '.join(f'{key}:{after[section][key]}' for key in added)}}}"
            )
        if changed:
            lines.append(
                f"{section}_changed={{{', '.join(f'{key}:{before[section][key]}->{after[section][key]}' for key in changed)}}}"
            )
    return lines or ["delta=none"]


def _summarize_degradation(ctx: PipelineContext, name: str) -> list[str]:
    candidates = getattr(ctx, "candidates", {}) or {}
    warning_keys = {
        "sam3": ("sam3_warnings",),
        "layout": ("layout_warnings",),
        "candidate_fusion": ("rmbg_warnings",),
    }.get(name, ())
    lines: list[str] = []
    for key in warning_keys:
        warnings = candidates.get(key) or []
        if not warnings:
            continue
        reasons = [
            str(item.get("reason", "unknown")) for item in warnings if isinstance(item, dict)
        ]
        details = _warning_details(warnings)
        suffix = f" details={details}" if details else ""
        lines.append(f"warnings={key}:{len(warnings)} reasons={reasons}{suffix}")
        lines.append("aborted=true")
    return lines


def _warning_details(warnings: list) -> list[str]:
    details: list[str] = []
    for item in warnings[:3]:
        if not isinstance(item, dict):
            continue
        message = item.get("message") or item.get("path") or item.get("sam3_src_path")
        if message:
            details.append(_shorten_warning_detail(str(message)))
    return details


def _shorten_warning_detail(value: str, limit: int = 180) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 3] + "..."
