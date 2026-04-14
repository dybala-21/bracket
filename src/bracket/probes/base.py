from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Probe(ABC):
    """Base class for host-side verification probes.

    Subclasses must implement name and execute(). The execute method
    must return a dict with at least 'probe_name', 'passed', and
    'detail' keys.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def execute(self) -> dict[str, Any]: ...
