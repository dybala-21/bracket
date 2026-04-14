from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bracket.core.contracts import ExecutionContract
from bracket.core.harness import Harness, RunHandle


class BaseAdapter(ABC):
    """Abstract base for framework-specific adapters.

    Subclasses translate framework lifecycle events into Bracket's
    canonical evidence model via the wrapped Harness.
    """

    def __init__(self, harness: Harness) -> None:
        self._harness = harness

    @property
    @abstractmethod
    def framework_name(self) -> str: ...

    @abstractmethod
    def wrap_run(self, contract: ExecutionContract, **kwargs: Any) -> RunHandle: ...

    @abstractmethod
    def finalize_run(self, run: RunHandle, **kwargs: Any) -> Any: ...
