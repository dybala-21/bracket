from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .events import EventType, EvidenceEvent, make_event_id, make_timestamp
from .policy import ActionKind, RiskLevel


class Resolution(Enum):
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ResolvedBy(Enum):
    USER = "user"
    POLICY = "policy"
    SYSTEM_TIMEOUT = "system_timeout"


@dataclass
class ApprovalRequest:
    action_kind: ActionKind
    resource: str
    risk_level: RiskLevel
    reason: str | None = None


@dataclass
class ApprovalResult:
    resolution: Resolution
    resolved_by: ResolvedBy
    reason: str | None = None


class ApprovalHandler(Protocol):
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult: ...


class AutoApproveHandler:
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        return ApprovalResult(resolution=Resolution.APPROVED, resolved_by=ResolvedBy.POLICY)


class AutoDenyHandler:
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        return ApprovalResult(resolution=Resolution.DENIED, resolved_by=ResolvedBy.POLICY)


class ApprovalBroker:
    """Bridges PolicyEngine ASK decisions to an ApprovalHandler.

    Owns approval semantics and canonical event creation. Adapters may
    implement the approval UI but must not bypass this broker.
    """

    def __init__(self, handler: ApprovalHandler | None = None) -> None:
        self._handler = handler or AutoApproveHandler()

    def request(
        self,
        action_kind: ActionKind,
        resource: str,
        risk_level: RiskLevel,
        run_id: str,
        seq_func: Callable[[], int],
        source_framework: str,
        reason: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[ApprovalResult, EvidenceEvent, EvidenceEvent]:
        """Submit an approval request and return the result with correlated events.

        Returns a (result, request_event, resolved_event) tuple. The two
        events share a correlation_id and should be appended to the
        evidence store by the caller.
        """
        req = ApprovalRequest(
            action_kind=action_kind,
            resource=resource,
            risk_level=risk_level,
            reason=reason,
        )

        request_event = EvidenceEvent(
            event_id=make_event_id(),
            run_id=run_id,
            seq=seq_func(),
            ts=make_timestamp(),
            event_type=EventType.APPROVAL_REQUESTED,
            source_framework=source_framework,
            correlation_id=correlation_id,
            payload={
                "action_kind": action_kind.value,
                "resource": resource,
                "risk_level": risk_level.value,
                "reason": reason,
            },
        )

        result = self._handler.request_approval(req)

        resolved_event = EvidenceEvent(
            event_id=make_event_id(),
            run_id=run_id,
            seq=seq_func(),
            ts=make_timestamp(),
            event_type=EventType.APPROVAL_RESOLVED,
            source_framework=source_framework,
            correlation_id=correlation_id,
            parent_event_id=request_event.event_id,
            payload={
                "resolution": result.resolution.value,
                "resolved_by": result.resolved_by.value,
                "reason": result.reason,
            },
        )

        return result, request_event, resolved_event
