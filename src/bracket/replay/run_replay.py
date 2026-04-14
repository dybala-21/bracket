from __future__ import annotations

from pathlib import Path
from typing import Any

from bracket.core.contracts import ExecutionContract
from bracket.core.events import EvidenceEvent
from bracket.core.evidence import EvidenceStore
from bracket.core.verdict import Verdict, VerdictEngine

from .serializers import read_json, read_jsonl


class TraceReplay:
    """Re-evaluates verdict from stored events without re-executing the external world."""

    def __init__(self, run_dir: str | Path) -> None:
        self._run_dir = Path(run_dir)

    def replay(self) -> Verdict:
        """Recompute the verdict from saved artifacts.

        Loads the contract, events, and probe results from disk and
        runs the verdict engine against them. Does not execute any
        external commands or probes.
        """
        contract_data = read_json(self._run_dir / "contract.json")
        events_data = read_jsonl(self._run_dir / "events.jsonl")
        probe_results = read_json(self._run_dir / "probes.json")

        contract = ExecutionContract.from_dict(contract_data)

        evidence = EvidenceStore()
        for event_data in events_data:
            evidence.append(EvidenceEvent.from_dict(event_data))

        return VerdictEngine().evaluate(contract, evidence, probe_results)


class ToolStubReplay:
    """Replays tool calls using stored results as stubs instead of re-executing."""

    def __init__(self, run_dir: str | Path) -> None:
        self._run_dir = Path(run_dir)

    def load_tool_stubs(self) -> dict[str, Any]:
        """Load tool call stubs keyed by correlation_id.

        Reads from tool_stubs.json if present, otherwise extracts
        stubs from the event log as a fallback.
        """
        stub_path = self._run_dir / "tool_stubs.json"
        if stub_path.exists():
            result: dict[str, Any] = read_json(stub_path)
            return result
        # Extract stubs from event log as fallback
        events = read_jsonl(self._run_dir / "events.jsonl")
        stubs: dict[str, Any] = {}
        for event in events:
            if event.get("event_type") in ("tool_succeeded", "tool_failed"):
                corr = event.get("correlation_id", "")
                if corr:
                    stubs[corr] = event.get("payload", {})
        return stubs
