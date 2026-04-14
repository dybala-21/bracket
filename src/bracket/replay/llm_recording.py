from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LLMCall:
    seq: int
    model: str
    request: dict[str, Any]
    response: dict[str, Any]
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "model": self.model,
            "request": self.request,
            "response": self.response,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMCall:
        return cls(
            seq=data["seq"],
            model=data["model"],
            request=data["request"],
            response=data["response"],
            duration_ms=data.get("duration_ms", 0),
        )


class LLMRecorder:
    """Records LLM request/response pairs for later playback or analysis."""

    def __init__(self) -> None:
        self._calls: list[LLMCall] = []
        self._seq = 0

    def record(
        self,
        model: str,
        request: dict[str, Any],
        response: dict[str, Any],
        duration_ms: int = 0,
    ) -> LLMCall:
        self._seq += 1
        call = LLMCall(seq=self._seq, model=model, request=request, response=response, duration_ms=duration_ms)
        self._calls.append(call)
        return call

    @property
    def calls(self) -> list[LLMCall]:
        return list(self._calls)

    def save(self, path: str | Path) -> None:
        """Persist recorded calls as JSON.

        The file may contain prompts and completions verbatim, including any
        secrets or PII passed through the LLM. Callers are responsible for
        redaction and for restricting access to the output directory.
        """
        p = Path(path)
        p.write_text(json.dumps([c.to_dict() for c in self._calls], indent=2, ensure_ascii=False))
        with contextlib.suppress(OSError):
            p.chmod(0o600)

    @classmethod
    def load(cls, path: str | Path) -> list[LLMCall]:
        data = json.loads(Path(path).read_text())
        return [LLMCall.from_dict(d) for d in data]
