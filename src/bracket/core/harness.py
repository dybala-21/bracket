from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .approval import ApprovalBroker, ApprovalHandler, Resolution
from .artifacts import ReplayManifest, RunArtifact
from .contracts import ExecutionContract
from .events import EventType, EvidenceEvent, make_event_id, make_timestamp
from .evidence import EvidenceStore
from .exceptions import BracketError
from .policy import ActionKind, PolicyDecision, PolicyEngine, PolicyRule
from .verdict import VerdictEngine


class RunHandle:
    """Handle to an active execution run.

    Created by Harness.start_run(). Records canonical evidence events
    during the run and enforces lifecycle constraints -- no events can
    be recorded after the run is finished.
    """

    def __init__(
        self,
        run_id: str,
        contract: ExecutionContract,
        evidence: EvidenceStore,
        policy: PolicyEngine,
        approval_broker: ApprovalBroker,
        source_framework: str = "generic",
    ) -> None:
        self.run_id = run_id
        self.contract = contract
        self.evidence = evidence
        self._policy = policy
        self._approval = approval_broker
        self._source_framework = source_framework
        self._finished = False

    @property
    def finished(self) -> bool:
        return self._finished

    def _guard_not_finished(self) -> None:
        if self._finished:
            raise BracketError(f"Run {self.run_id} is already finished")

    def emit(self, event_type: EventType, payload: dict[str, Any], **kwargs: Any) -> EvidenceEvent:
        """Create and append a raw evidence event.

        Lower-level than the record_* methods. Does not enforce the
        finished guard so the harness can emit probe events after the
        run ends. Prefer record_* methods for normal evidence recording.
        """
        event = EvidenceEvent(
            event_id=make_event_id(),
            run_id=self.run_id,
            seq=self.evidence.next_seq(),
            ts=make_timestamp(),
            event_type=event_type,
            source_framework=self._source_framework,
            payload=payload,
            **kwargs,
        )
        self.evidence.append(event)
        return event

    def record_model_called(
        self,
        model: str,
        request_ref: str = "",
        response_ref: str = "",
        duration_ms: int | None = None,
        **extra: Any,
    ) -> EvidenceEvent:
        """Record an LLM model invocation.

        Use *_ref parameters to point to stored request/response payloads
        rather than embedding them inline.
        """
        self._guard_not_finished()
        payload: dict[str, Any] = {
            "model": model,
            "request_ref": request_ref,
            "response_ref": response_ref,
            **extra,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return self.emit(EventType.MODEL_CALLED, payload)

    def record_file_read(
        self,
        path: str,
        source: str = "tool",
        byte_count: int = 0,
        **extra: Any,
    ) -> EvidenceEvent:
        """Record a file read. Required for the read-before-write check.

        source is one of: 'tool', 'runtime_cache', 'user_supplied'.
        """
        self._guard_not_finished()
        payload = {"path": path, "source": source, "byte_count": byte_count, **extra}
        return self.emit(EventType.FILE_READ, payload)

    def record_file_changed(
        self,
        path: str,
        change_kind: str = "update",
        artifact_ref: str = "",
        **extra: Any,
    ) -> EvidenceEvent:
        """Record a file change.

        change_kind is one of: 'create', 'update', 'delete', 'rename'.
        For an existing file, record_file_read() must be called first
        to satisfy the read-before-write requirement.
        """
        self._guard_not_finished()
        payload = {"path": path, "change_kind": change_kind, "artifact_ref": artifact_ref, **extra}
        return self.emit(EventType.FILE_CHANGED, payload)

    def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> EvidenceEvent:
        """Record the start of a tool invocation.

        Returns the event whose correlation_id should be passed to the
        subsequent record_tool_success() or record_tool_failure() call
        to link the pair.
        """
        self._guard_not_finished()
        corr = correlation_id or f"corr_{uuid.uuid4().hex[:8]}"
        payload: dict[str, Any] = {"tool_name": tool_name, "arguments_ref": ""}
        if arguments is not None:
            payload["arguments"] = arguments
        return self.emit(EventType.TOOL_CALLED, payload, correlation_id=corr)

    def record_tool_success(
        self,
        tool_name: str,
        result_ref: str = "",
        correlation_id: str | None = None,
        duration_ms: int | None = None,
    ) -> EvidenceEvent:
        self._guard_not_finished()
        payload: dict[str, Any] = {
            "tool_name": tool_name,
            "arguments_ref": "",
            "result_ref": result_ref,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return self.emit(EventType.TOOL_SUCCEEDED, payload, correlation_id=correlation_id)

    def record_tool_failure(
        self,
        tool_name: str,
        error_kind: str = "runtime_error",
        error_ref: str = "",
        correlation_id: str | None = None,
    ) -> EvidenceEvent:
        self._guard_not_finished()
        payload = {
            "tool_name": tool_name,
            "arguments_ref": "",
            "error_kind": error_kind,
            "error_ref": error_ref,
        }
        return self.emit(EventType.TOOL_FAILED, payload, correlation_id=correlation_id)

    def record_command(
        self,
        command: str,
        exit_code: int = 0,
        kind: str = "inspection",
        stdout_ref: str = "",
        stderr_ref: str = "",
        cwd: str = ".",
        correlation_id: str | None = None,
    ) -> tuple[EvidenceEvent, EvidenceEvent]:
        """Emit COMMAND_EXECUTED and COMMAND_RESULT_RECORDED, tied by correlation_id.

        kind is one of: 'verification', 'mutation', 'inspection', 'setup'.
        """
        self._guard_not_finished()
        corr = correlation_id or f"corr_{uuid.uuid4().hex[:8]}"

        exec_event = self.emit(
            EventType.COMMAND_EXECUTED,
            {"command": command, "cwd": cwd, "kind": kind},
            correlation_id=corr,
        )
        result_event = self.emit(
            EventType.COMMAND_RESULT_RECORDED,
            {
                "command": command,
                "exit_code": exit_code,
                "stdout_ref": stdout_ref,
                "stderr_ref": stderr_ref,
                "kind": kind,
            },
            correlation_id=corr,
            parent_event_id=exec_event.event_id,
        )
        return exec_event, result_event

    def record_web_fetch(
        self,
        url: str,
        method: str = "GET",
        status_code: int = 200,
        content_ref: str = "",
        **extra: Any,
    ) -> EvidenceEvent:
        self._guard_not_finished()
        payload = {
            "url": url,
            "method": method,
            "status_code": status_code,
            "content_ref": content_ref,
            **extra,
        }
        return self.emit(EventType.WEB_FETCHED, payload)

    def record_artifact(self, artifact_id: str, ref: str, kind: str = "file") -> EvidenceEvent:
        self._guard_not_finished()
        payload = {"artifact_id": artifact_id, "ref": ref, "kind": kind}
        return self.emit(EventType.ARTIFACT_EMITTED, payload)

    def check_policy(self, action_kind: ActionKind, resource: str) -> PolicyDecision:
        """Evaluate the policy for an action against a resource.

        Returns the final decision: ALLOW passes, DENY blocks, and ASK
        is routed through the approval broker for resolution. Both DENY
        and ASK-denied emit APPROVAL_RESOLVED into the evidence store so
        the policy.no_hard_failures requirement picks them up.
        """
        decision, risk_level = self._policy.evaluate(action_kind, resource)

        if decision == PolicyDecision.ASK:
            corr = f"corr_{uuid.uuid4().hex[:8]}"
            result, req_event, res_event = self._approval.request(
                action_kind=action_kind,
                resource=resource,
                risk_level=risk_level,
                run_id=self.run_id,
                seq_func=self.evidence.next_seq,
                source_framework=self._source_framework,
                correlation_id=corr,
            )
            self.evidence.append(req_event)
            self.evidence.append(res_event)

            if result.resolution == Resolution.APPROVED:
                return PolicyDecision.ALLOW
            return PolicyDecision.DENY

        if decision == PolicyDecision.DENY:
            self.emit(
                EventType.APPROVAL_RESOLVED,
                {
                    "resolution": "denied",
                    "resolved_by": "policy",
                    "action_kind": action_kind.value,
                    "resource": resource,
                    "risk_level": risk_level.value,
                    "reason": None,
                },
            )

        return decision

    def mark_finished(self, final_output: str | None = None) -> EvidenceEvent:
        """Mark the run as finished and emit a RUN_FINISHED event.

        After this call, all record_* methods will raise BracketError.
        Typically called by Harness.finish_run_sync() rather than directly.
        """
        self._guard_not_finished()
        self._finished = True
        return self.emit(EventType.RUN_FINISHED, {"final_output": final_output})


def _make_run_id() -> str:
    now = datetime.now(UTC).strftime("%Y%m%d")
    short = uuid.uuid4().hex[:8]
    return f"run_{now}_{short}"


class Harness:
    """Main entry point for Bracket execution assurance.

    Manages run lifecycle, policy evaluation, verdict computation,
    probe execution, and artifact persistence. Framework-agnostic --
    use adapters for framework-specific integration.

    Example::

        harness = Harness(app_name="my-agent", artifact_dir=".bracket")
        run = harness.start_run(contract)
        run.record_file_read("app.py", byte_count=1842)
        run.record_file_changed("app.py")
        result = harness.finish_run_sync(run, final_output="Done.")
    """

    def __init__(
        self,
        app_name: str = "bracket",
        artifact_dir: str = ".bracket",
        source_framework: str = "generic",
        policy_rules: list[PolicyRule] | None = None,
        approval_handler: ApprovalHandler | None = None,
    ) -> None:
        self.app_name = app_name
        self.artifact_dir = Path(artifact_dir)
        self._source_framework = source_framework
        self._policy = PolicyEngine(rules=policy_rules)
        self._approval = ApprovalBroker(handler=approval_handler)
        self._verdict_engine = VerdictEngine()
        self._on_run_start: list[Any] = []
        self._on_run_end: list[Any] = []

    def on_run_start(self, callback: Any) -> None:
        """Callback receives keyword arguments ``run`` and ``contract``."""
        self._on_run_start.append(callback)

    def on_run_end(self, callback: Any) -> None:
        """Callback receives keyword argument ``artifact``."""
        self._on_run_end.append(callback)

    def start_run(self, contract: ExecutionContract) -> RunHandle:
        """Begin a new execution run for the given contract.

        Returns a RunHandle used to record evidence events. A
        RUN_STARTED event is emitted automatically.
        """
        run_id = _make_run_id()
        evidence = EvidenceStore()
        run = RunHandle(
            run_id=run_id,
            contract=contract,
            evidence=evidence,
            policy=self._policy,
            approval_broker=self._approval,
            source_framework=self._source_framework,
        )
        run.emit(EventType.RUN_STARTED, {"goal": contract.goal, "profile_id": contract.profile_id})
        for cb in self._on_run_start:
            cb(run=run, contract=contract)
        return run

    def finish_run_sync(
        self,
        run: RunHandle,
        final_output: str | None = None,
        probes: list[Any] | None = None,
    ) -> RunArtifact:
        """Finish the run, execute any probes, and compute the verdict."""
        if not run.finished:
            run.mark_finished(final_output=final_output)

        probe_results: list[dict[str, Any]] = []
        if probes:
            for probe in probes:
                result = probe.execute()
                probe_results.append(result)
                run.emit(
                    EventType.PROBE_COMPLETED,
                    {"probe_name": result.get("probe_name", "unknown"), **result},
                )

        verdict = self._verdict_engine.evaluate(run.contract, run.evidence, probe_results)
        summary = run.evidence.compute_summary()

        manifest = ReplayManifest(
            run_id=run.run_id,
            requirement_set_version=f"{run.contract.profile_id}@{run.contract.requirement_set_version}",
            adapter_version=f"{self._source_framework}@0.1.0",
            supported_modes=["trace_replay", "tool_stub_replay"],
        )

        artifact = RunArtifact(
            run_id=run.run_id,
            contract=run.contract,
            events=run.evidence.events,
            summary=summary,
            probe_results=probe_results,
            verdict=verdict,
            replay_manifest=manifest,
            metadata={"app_name": self.app_name},
        )

        artifact.save(self.artifact_dir)
        for cb in self._on_run_end:
            cb(artifact=artifact)
        return artifact
