from __future__ import annotations
from typing import Protocol


class LazyModel(Protocol):
    def load(self) -> object: ...
