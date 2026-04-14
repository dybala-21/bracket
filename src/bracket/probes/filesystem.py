from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Probe

_MAX_READ_BYTES = 10 * 1024 * 1024


class FilesystemProbe(Probe):
    def __init__(
        self,
        path: str,
        should_exist: bool = True,
        contains: str | None = None,
        not_contains: str | None = None,
    ) -> None:
        self._path = path
        self._should_exist = should_exist
        self._contains = contains
        self._not_contains = not_contains

    @property
    def name(self) -> str:
        return "filesystem"

    def execute(self) -> dict[str, Any]:
        p = Path(self._path)
        exists = p.exists()

        if self._should_exist and not exists:
            return self._fail(f"Expected file {self._path} to exist but it does not")

        if not self._should_exist and exists:
            return self._fail(f"Expected file {self._path} to not exist but it does")

        content: str | None = None
        if exists and (self._contains is not None or self._not_contains is not None):
            try:
                with p.open("rb") as fh:
                    content = fh.read(_MAX_READ_BYTES).decode("utf-8", errors="replace")
            except OSError as e:
                return self._fail(f"Failed to read {self._path}: {e}")

        if content is not None and self._contains is not None and self._contains not in content:
            return self._fail(f"File {self._path} does not contain expected string")

        if content is not None and self._not_contains is not None and self._not_contains in content:
            return self._fail(f"File {self._path} contains unexpected string")

        return {
            "probe_name": self.name,
            "passed": True,
            "detail": f"File {self._path} check passed",
            "path": self._path,
        }

    def _fail(self, detail: str) -> dict[str, Any]:
        return {"probe_name": self.name, "passed": False, "detail": detail, "path": self._path}
