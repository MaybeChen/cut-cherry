from __future__ import annotations

import re

from image2pptx.pipeline.context import PipelineContext

_FORMULA_RE = re.compile(
    r"(=|\\b(?:sum|avg|min|max|sqrt|sin|cos|tan|log)\\b|[∑√π≈≤≥±×÷]|[A-Za-z0-9)][+\-*/^=][A-Za-z0-9(])",
    re.IGNORECASE,
)


class FormulaProcessor:
    """Detect formula-like OCR text blocks for editable formula fallback rendering."""

    def run(self, ctx: PipelineContext) -> None:
        text_candidates = ctx.candidates.get("text_blocks") or ctx.candidates.get("text", [])
        formulas = []
        for item in text_candidates:
            text = str(item.get("text", "")).strip()
            if not text or not _looks_like_formula(text):
                continue
            formulas.append(
                {
                    "id": f"formula_{len(formulas)}",
                    "kind": "formula",
                    "text": text,
                    "bbox": item["bbox"],
                    "confidence": min(float(item.get("confidence", 0.0)), 0.8),
                    "source_ids": item.get("source_ids", [item.get("id", "text")]),
                    "raw_text_block": item,
                }
            )
        ctx.candidates["formulas"] = formulas


class TODOProcessor(FormulaProcessor):
    """Backward-compatible alias for the old extension-point class name."""


def _looks_like_formula(text: str) -> bool:
    compact = "".join(text.split())
    if len(compact) < 3:
        return False
    if _FORMULA_RE.search(compact):
        return True
    operator_count = sum(compact.count(op) for op in ("+", "-", "*", "/", "=", "^"))
    digit_count = sum(ch.isdigit() for ch in compact)
    return operator_count >= 2 and digit_count >= 1
