"""Optional model adapter. Heavy dependencies are imported only inside load/infer methods."""

from __future__ import annotations


class OptionalModelAdapter:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def available(self) -> bool:
        return self.enabled
