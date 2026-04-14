from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .events import EventType, EvidenceEvent
from .exceptions import EvidenceError


@dataclass
class EvidenceSummary:
    total_events: int = 0
    file_reads: list[str] = field(default_factory=list)
    file_changes: list[str] = field(default_factory=list)
    commands_executed: int = 0
    verification_commands: int = 0
    web_fetches: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    approvals_requested: int = 0
    approvals_denied: int = 0
    probes_completed: int = 0
    artifacts_emitted: int = 0
    hard_failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "file_reads": self.file_reads,
            "file_changes": self.file_changes,
            "commands_executed": self.commands_executed,
            "verification_commands": self.verification_commands,
            "web_fetches": self.web_fetches,
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "approvals_requested": self.approvals_requested,
            "approvals_denied": self.approvals_denied,
            "probes_completed": self.probes_completed,
            "artifacts_emitted": self.artifacts_emitted,
            "hard_failures": self.hard_failures,
        }


_KNOWN_PROJECTIONS = frozenset(
    {
        "file_read_before_file_changed",
        "file_changed_count",
        "file_read_count",
        "execution_count",
        "verification_count",
        "web_fetch_count",
        "grounding_count",
        "hard_failure_count",
        "intent_resolved",
        "file_artifact_count",
    }
)


class EvidenceStore:
    """Append-only store for canonical evidence events.

    Provides summary computation and named projections used by the
    verdict engine to evaluate requirements.
    """

    def __init__(self) -> None:
        self._events: list[EvidenceEvent] = []
        self._seq_counter: int = 0

    @property
    def events(self) -> list[EvidenceEvent]:
        return list(self._events)

    def next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter

    def append(self, event: EvidenceEvent) -> None:
        self._events.append(event)

    def get_events_by_type(self, event_type: EventType) -> list[EvidenceEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def compute_summary(self) -> EvidenceSummary:
        summary = EvidenceSummary(total_events=len(self._events))

        for event in self._events:
            match event.event_type:
                case EventType.FILE_READ:
                    path = event.payload.get("path", "")
                    if path and path not in summary.file_reads:
                        summary.file_reads.append(path)

                case EventType.FILE_CHANGED:
                    path = event.payload.get("path", "")
                    if path and path not in summary.file_changes:
                        summary.file_changes.append(path)

                case EventType.COMMAND_EXECUTED:
                    summary.commands_executed += 1

                case EventType.COMMAND_RESULT_RECORDED:
                    if event.payload.get("kind") == "verification":
                        summary.verification_commands += 1

                case EventType.WEB_FETCHED:
                    summary.web_fetches += 1

                case EventType.TOOL_SUCCEEDED:
                    summary.tool_successes += 1

                case EventType.TOOL_FAILED:
                    summary.tool_failures += 1
                    error_kind = event.payload.get("error_kind", "unknown")
                    if error_kind in ("permission_denied",):
                        summary.hard_failures.append(f"tool_failed:{event.payload.get('tool_name', 'unknown')}")

                case EventType.APPROVAL_REQUESTED:
                    summary.approvals_requested += 1

                case EventType.APPROVAL_RESOLVED:
                    if event.payload.get("resolution") == "denied":
                        summary.approvals_denied += 1
                        summary.hard_failures.append(f"approval_denied:{event.payload.get('resolved_by', 'unknown')}")

                case EventType.PROBE_COMPLETED:
                    summary.probes_completed += 1

                case EventType.ARTIFACT_EMITTED:
                    summary.artifacts_emitted += 1

        return summary

    def compute_projection(self, projection_name: str) -> dict[str, Any]:
        """Compute a named projection from the event log.

        Projections produce the intermediate dict that predicates
        evaluate against. Raises EvidenceError for unknown names.
        """
        if projection_name not in _KNOWN_PROJECTIONS:
            raise EvidenceError(f"Unknown projection: {projection_name!r}")

        match projection_name:
            case "file_read_before_file_changed":
                return self._project_file_read_before_changed()
            case "file_changed_count":
                return {"count": len(self.get_events_by_type(EventType.FILE_CHANGED))}
            case "file_read_count":
                return {"count": len(self.get_events_by_type(EventType.FILE_READ))}
            case "execution_count":
                count = len(self.get_events_by_type(EventType.COMMAND_EXECUTED)) + len(
                    self.get_events_by_type(EventType.TOOL_SUCCEEDED)
                )
                return {"count": count}
            case "verification_count":
                count = sum(
                    1
                    for e in self.get_events_by_type(EventType.COMMAND_RESULT_RECORDED)
                    if e.payload.get("kind") == "verification"
                )
                return {"count": count}
            case "web_fetch_count":
                return {"count": len(self.get_events_by_type(EventType.WEB_FETCHED))}
            case "grounding_count":
                count = (
                    len(self.get_events_by_type(EventType.FILE_READ))
                    + len(self.get_events_by_type(EventType.WEB_FETCHED))
                    + len(self.get_events_by_type(EventType.COMMAND_RESULT_RECORDED))
                )
                return {"count": count}
            case "hard_failure_count":
                summary = self.compute_summary()
                return {"count": len(summary.hard_failures)}
            case "intent_resolved":
                finished = self.get_events_by_type(EventType.RUN_FINISHED)
                if finished:
                    output = finished[-1].payload.get("final_output")
                    return {"resolved": output if output else None}
                return {"resolved": None}
            case "file_artifact_count":
                return {"count": len(self.get_events_by_type(EventType.ARTIFACT_EMITTED))}
            case _:
                raise EvidenceError(f"Unhandled projection: {projection_name!r}")

    def _project_file_read_before_changed(self) -> dict[str, Any]:
        read_paths: set[str] = set()
        matches = 0
        violations: list[str] = []

        for event in self._events:
            if event.event_type == EventType.FILE_READ:
                path = event.payload.get("path", "")
                if path:
                    read_paths.add(path)
            elif event.event_type == EventType.FILE_CHANGED:
                path = event.payload.get("path", "")
                if path:
                    if path in read_paths:
                        matches += 1
                    else:
                        violations.append(path)

        return {"matches": matches, "violations": violations}
