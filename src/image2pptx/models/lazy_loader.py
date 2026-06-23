from __future__ import annotations
from threading import Lock
from typing import Callable, Generic, TypeVar
T=TypeVar('T')
class LazyLoader(Generic[T]):
    def __init__(self, factory: Callable[[], T]) -> None:
        self.factory=factory; self._value:T|None=None; self._lock=Lock()
    def get(self) -> T:
        if self._value is None:
            with self._lock:
                if self._value is None: self._value=self.factory()
        return self._value
