from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import Probe


class CustomProbe(Probe):
    """User-defined probe backed by an arbitrary callable.

    The callable should return a dict with at least 'passed' and
    'detail' keys. Exceptions are caught and reported as failures.
    """

    def __init__(
        self,
        name: str,
        check: Callable[[], dict[str, Any]],
    ) -> None:
        self._name = name
        self._check = check

    @property
    def name(self) -> str:
        return self._name

    def execute(self) -> dict[str, Any]:
        try:
            result = self._check()
            if "probe_name" not in result:
                result["probe_name"] = self._name
            if "passed" not in result:
                result["passed"] = False
            return result
        except Exception as exc:
            return {
                "probe_name": self._name,
                "passed": False,
                "detail": f"Custom probe raised: {exc}",
            }
