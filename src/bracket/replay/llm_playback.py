from __future__ import annotations

from typing import Any

from bracket.core.exceptions import ReplayError

from .llm_recording import LLMCall


class LLMPlayback:
    """Replays recorded LLM responses in sequence.

    Raises ReplayError when all recorded calls have been consumed.
    """

    def __init__(self, calls: list[LLMCall]) -> None:
        self._calls = list(calls)
        self._index = 0

    def next_response(self) -> dict[str, Any]:
        if self._index >= len(self._calls):
            raise ReplayError("No more recorded LLM calls")
        call = self._calls[self._index]
        self._index += 1
        return call.response

    @property
    def remaining(self) -> int:
        return len(self._calls) - self._index

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._calls)
