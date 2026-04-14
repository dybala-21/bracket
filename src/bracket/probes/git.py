from __future__ import annotations

import subprocess
from typing import Any

from .base import Probe


class GitDiffProbe(Probe):
    def __init__(
        self,
        expected_files: list[str] | None = None,
        cwd: str = ".",
        staged: bool = False,
    ) -> None:
        self._expected_files = expected_files
        self._cwd = cwd
        self._staged = staged

    @property
    def name(self) -> str:
        return "git_diff"

    def execute(self) -> dict[str, Any]:
        cmd = ["git", "diff", "--name-only"]
        if self._staged:
            cmd.append("--staged")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=self._cwd)
        except Exception as exc:
            return {"probe_name": self.name, "passed": False, "detail": f"git diff failed: {exc}"}

        changed_files = [f for f in result.stdout.strip().split("\n") if f]

        if self._expected_files is None:
            passed = len(changed_files) > 0
            detail = f"{len(changed_files)} files changed"
        else:
            missing = [f for f in self._expected_files if f not in changed_files]
            passed = len(missing) == 0
            detail = f"changed={changed_files}, missing={missing}"

        return {"probe_name": self.name, "passed": passed, "detail": detail, "changed_files": changed_files}
