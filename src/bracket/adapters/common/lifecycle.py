from __future__ import annotations

from collections.abc import Callable
from typing import Any


class LifecycleHook:
    """Simple callback registry for run start and end events."""

    def __init__(self) -> None:
        self._on_run_start: list[Callable[..., None]] = []
        self._on_run_end: list[Callable[..., None]] = []

    def on_run_start(self, callback: Callable[..., None]) -> None:
        self._on_run_start.append(callback)

    def on_run_end(self, callback: Callable[..., None]) -> None:
        self._on_run_end.append(callback)

    def fire_run_start(self, **kwargs: Any) -> None:
        for cb in self._on_run_start:
            cb(**kwargs)

    def fire_run_end(self, **kwargs: Any) -> None:
        for cb in self._on_run_end:
            cb(**kwargs)
