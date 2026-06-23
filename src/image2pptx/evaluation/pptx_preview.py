from __future__ import annotations
from pathlib import Path
from typing import Protocol
class PptxPreviewRenderer(Protocol):
    def render(self, pptx_path: Path, output_dir: Path) -> list[Path]: ...
class LibreOfficePreviewRenderer:
    def render(self, pptx_path: Path, output_dir: Path) -> list[Path]:
        raise NotImplementedError("Phase 4 TODO: LibreOffice headless preview rendering")
