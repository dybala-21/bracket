from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from .base import Probe


class HTTPProbe(Probe):
    def __init__(
        self,
        url: str,
        method: str = "GET",
        expected_status: int = 200,
        contains: str | None = None,
        timeout: int = 30,
    ) -> None:
        self._url = url
        self._method = method
        self._expected_status = expected_status
        self._contains = contains
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "http"

    def execute(self) -> dict[str, Any]:
        try:
            req = urllib.request.Request(self._url, method=self._method)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")[:8192]
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read().decode("utf-8", errors="replace")[:8192]
        except Exception as exc:
            return {"probe_name": self.name, "passed": False, "detail": f"HTTP request failed: {exc}", "url": self._url}

        passed = status == self._expected_status
        detail = f"status={status}"

        if passed and self._contains is not None and self._contains not in body:
            passed = False
            detail += f"; body does not contain '{self._contains}'"

        return {"probe_name": self.name, "passed": passed, "detail": detail, "url": self._url, "status_code": status}
