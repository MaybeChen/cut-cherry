from __future__ import annotations
import shutil
import cv2
import numpy as np
from PIL import Image, ImageOps
from image2pptx.core.errors import InputValidationError
from image2pptx.pipeline.context import PipelineContext


class PreprocessProcessor:
    def run(self, ctx: PipelineContext) -> None:
        if ctx.input_path.suffix.lower() == ".pdf":
            raise InputValidationError(
                "PDF rendering is reserved for Phase 2; provide a page image in Phase 1"
            )
        image = Image.open(ctx.input_path)
        image.verify()
        image = Image.open(ctx.input_path)
        image = ImageOps.exif_transpose(image).convert("RGBA" if image.mode == "RGBA" else "RGB")
        ctx.job_dir.mkdir(parents=True, exist_ok=True)
        source = ctx.job_dir / "source.png"
        normalized = ctx.job_dir / "normalized.png"
        shutil.copyfile(ctx.input_path, source)
        image.save(normalized)
        arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        cv2.imwrite(str(ctx.job_dir / "gray.png"), gray)
        cv2.imwrite(str(ctx.job_dir / "edges.png"), edges)
        cv2.imwrite(str(ctx.job_dir / "lab.png"), cv2.cvtColor(arr, cv2.COLOR_BGR2LAB))
        cv2.imwrite(str(ctx.job_dir / "hsv.png"), cv2.cvtColor(arr, cv2.COLOR_BGR2HSV))
        image.convert("RGB").save(ctx.job_dir / "preview.png")
        ctx.artifacts.update(
            {
                "source": source,
                "normalized": normalized,
                "gray": ctx.job_dir / "gray.png",
                "edges": ctx.job_dir / "edges.png",
            }
        )
