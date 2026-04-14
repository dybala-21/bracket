from __future__ import annotations

import subprocess
from typing import Any

from .base import Probe


class CommandProbe(Probe):
    def __init__(
        self,
        command: str | list[str],
        expected_exit_code: int = 0,
        timeout: int = 60,
        contains: str | None = None,
        cwd: str | None = None,
    ) -> None:
        self._command = command
        self._expected_exit_code = expected_exit_code
        self._timeout = timeout
        self._contains = contains
        self._cwd = cwd

    @property
    def name(self) -> str:
        return "command"

    def execute(self) -> dict[str, Any]:
        try:
            result = subprocess.run(
                self._command,
                shell=isinstance(self._command, str),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=self._cwd,
            )
        except subprocess.TimeoutExpired:
            return {
                "probe_name": self.name,
                "passed": False,
                "detail": f"Command timed out after {self._timeout}s",
                "command": self._command,
            }
        except Exception as exc:
            return {
                "probe_name": self.name,
                "passed": False,
                "detail": f"Command execution failed: {exc}",
                "command": self._command,
            }

        passed = result.returncode == self._expected_exit_code
        detail = f"exit_code={result.returncode}"

        if passed and self._contains is not None and self._contains not in result.stdout:
            passed = False
            detail += f"; stdout does not contain '{self._contains}'"

        return {
            "probe_name": self.name,
            "passed": passed,
            "detail": detail,
            "command": self._command,
            "exit_code": result.returncode,
            "stdout": result.stdout[:4096],
            "stderr": result.stderr[:4096],
        }
