from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    RUN_STARTED = "run_started"
    MODEL_CALLED = "model_called"
    TOOL_CALLED = "tool_called"
    TOOL_SUCCEEDED = "tool_succeeded"
    TOOL_FAILED = "tool_failed"
    FILE_READ = "file_read"
    FILE_CHANGED = "file_changed"
    WEB_FETCHED = "web_fetched"
    COMMAND_EXECUTED = "command_executed"
    COMMAND_RESULT_RECORDED = "command_result_recorded"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    PROBE_COMPLETED = "probe_completed"
    ARTIFACT_EMITTED = "artifact_emitted"
    RUN_FINISHED = "run_finished"


@dataclass
class RedactionInfo:
    applied: bool = False
    rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"applied": self.applied, "rules": self.rules}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RedactionInfo:
        return cls(applied=data.get("applied", False), rules=data.get("rules", []))


@dataclass
class EvidenceEvent:
    """Canonical evidence event envelope.

    All execution evidence is normalized into this structure regardless
    of the source framework. The payload schema varies by event_type.
    """

    event_id: str
    run_id: str
    seq: int
    ts: str
    event_type: EventType
    source_framework: str
    payload: dict[str, Any]

    session_id: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None
    parent_event_id: str | None = None
    actor: str | None = None
    source_span_id: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    redaction: RedactionInfo = field(default_factory=RedactionInfo)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "seq": self.seq,
            "ts": self.ts,
            "event_type": self.event_type.value,
            "source_framework": self.source_framework,
            "payload": self.payload,
        }
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.thread_id is not None:
            d["thread_id"] = self.thread_id
        if self.correlation_id is not None:
            d["correlation_id"] = self.correlation_id
        if self.parent_event_id is not None:
            d["parent_event_id"] = self.parent_event_id
        if self.actor is not None:
            d["actor"] = self.actor
        if self.source_span_id is not None:
            d["source_span_id"] = self.source_span_id
        if self.artifact_refs:
            d["artifact_refs"] = self.artifact_refs
        d["redaction"] = self.redaction.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceEvent:
        redaction_data = data.get("redaction", {})
        return cls(
            event_id=data["event_id"],
            run_id=data["run_id"],
            seq=data["seq"],
            ts=data["ts"],
            event_type=EventType(data["event_type"]),
            source_framework=data["source_framework"],
            payload=data["payload"],
            session_id=data.get("session_id"),
            thread_id=data.get("thread_id"),
            correlation_id=data.get("correlation_id"),
            parent_event_id=data.get("parent_event_id"),
            actor=data.get("actor"),
            source_span_id=data.get("source_span_id"),
            artifact_refs=data.get("artifact_refs", []),
            redaction=RedactionInfo.from_dict(redaction_data),
        )


def make_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def make_timestamp() -> str:
    return datetime.now(UTC).isoformat()
