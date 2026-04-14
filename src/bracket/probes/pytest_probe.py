from __future__ import annotations

import subprocess
from typing import Any

from .base import Probe


class PytestProbe(Probe):
    def __init__(
        self,
        target: str = ".",
        args: list[str] | None = None,
        timeout: int = 120,
        cwd: str | None = None,
    ) -> None:
        self._target = target
        self._args = args or []
        self._timeout = timeout
        self._cwd = cwd

    @property
    def name(self) -> str:
        return "pytest"

    def execute(self) -> dict[str, Any]:
        cmd = ["python", "-m", "pytest", self._target, "-v", *self._args]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout, cwd=self._cwd)
        except subprocess.TimeoutExpired:
            return {
                "probe_name": self.name,
                "passed": False,
                "detail": f"pytest timed out after {self._timeout}s",
                "target": self._target,
            }
        except Exception as exc:
            return {
                "probe_name": self.name,
                "passed": False,
                "detail": f"pytest execution failed: {exc}",
                "target": self._target,
            }

        return {
            "probe_name": self.name,
            "passed": result.returncode == 0,
            "detail": f"exit_code={result.returncode}",
            "target": self._target,
            "exit_code": result.returncode,
            "stdout": result.stdout[:8192],
            "stderr": result.stderr[:8192],
        }
