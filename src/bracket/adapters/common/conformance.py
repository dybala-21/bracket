from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bracket.core.events import EventType, EvidenceEvent


@dataclass
class ConformanceViolation:
    rule: str
    detail: str


@dataclass
class ConformanceReport:
    passed: bool
    violations: list[ConformanceViolation] = field(default_factory=list)
    missing_events: list[str] = field(default_factory=list)
    field_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [{"rule": v.rule, "detail": v.detail} for v in self.violations],
            "missing_events": self.missing_events,
            "field_violations": self.field_violations,
        }


class ConformanceChecker:
    """Validates that an event log meets the canonical evidence contract.

    Checks required event types per profile, monotonic seq ordering,
    required field presence, and correlation pair completeness.
    """

    def check(self, events: list[EvidenceEvent], profile_id: str) -> ConformanceReport:
        violations: list[ConformanceViolation] = []
        missing_events: list[str] = []
        field_violations: list[str] = []

        required = self._required_event_types(profile_id)
        emitted_types = {e.event_type for e in events}
        for req_type in required:
            if req_type not in emitted_types:
                missing_events.append(req_type.value)

        seqs = [e.seq for e in events]
        for i in range(1, len(seqs)):
            if seqs[i] <= seqs[i - 1]:
                violations.append(
                    ConformanceViolation(rule="seq_monotonic", detail=f"seq {seqs[i]} not > {seqs[i - 1]} at index {i}")
                )

        for event in events:
            if not event.event_id:
                field_violations.append(f"seq={event.seq}: missing event_id")
            if not event.run_id:
                field_violations.append(f"seq={event.seq}: missing run_id")
            if not event.ts:
                field_violations.append(f"seq={event.seq}: missing ts")
            if not event.source_framework:
                field_violations.append(f"seq={event.seq}: missing source_framework")

        self._check_correlation_pairs(events, violations)

        passed = not violations and not missing_events and not field_violations
        return ConformanceReport(
            passed=passed, violations=violations, missing_events=missing_events, field_violations=field_violations
        )

    def _required_event_types(self, profile_id: str) -> list[EventType]:
        base = [EventType.RUN_STARTED, EventType.RUN_FINISHED]
        match profile_id:
            case "code_change":
                return [*base, EventType.FILE_READ, EventType.FILE_CHANGED, EventType.COMMAND_RESULT_RECORDED]
            case "research":
                return [*base, EventType.FILE_READ, EventType.WEB_FETCHED]
            case "file_task":
                return [*base, EventType.FILE_CHANGED, EventType.ARTIFACT_EMITTED]
            case _:
                return base

    def _check_correlation_pairs(self, events: list[EvidenceEvent], violations: list[ConformanceViolation]) -> None:
        pairs: list[tuple[EventType, set[EventType]]] = [
            (EventType.COMMAND_EXECUTED, {EventType.COMMAND_RESULT_RECORDED}),
            (EventType.APPROVAL_REQUESTED, {EventType.APPROVAL_RESOLVED}),
            (EventType.TOOL_CALLED, {EventType.TOOL_SUCCEEDED, EventType.TOOL_FAILED}),
        ]
        for start_type, end_types in pairs:
            start_corrs = {e.correlation_id for e in events if e.event_type == start_type and e.correlation_id}
            end_corrs = {e.correlation_id for e in events if e.event_type in end_types and e.correlation_id}
            end_label = " | ".join(sorted(t.value for t in end_types))
            for corr in start_corrs - end_corrs:
                violations.append(
                    ConformanceViolation(
                        rule="correlation_pair",
                        detail=f"{start_type.value} correlation_id={corr} has no matching {end_label}",
                    )
                )
