"""Core integration tests — verifies the full Bracket pipeline."""

import json
import tempfile
from pathlib import Path

from bracket.core.contracts import ExecutionContract
from bracket.core.events import EventType
from bracket.core.evidence import EvidenceStore
from bracket.core.harness import Harness
from bracket.core.requirements import Predicate, PredicateOp, RequirementKind, RequirementSpec
from bracket.core.verdict import VerdictEngine, VerdictOutcome


class TestRequirementSpec:
    def test_predicate_count_gte(self):
        p = Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1)
        assert p.evaluate({"count": 2}) is True
        assert p.evaluate({"count": 0}) is False

    def test_predicate_exists(self):
        p = Predicate(op=PredicateOp.EXISTS, field="resolved", value=True)
        assert p.evaluate({"resolved": True}) is True
        assert p.evaluate({"resolved": None}) is False
        assert p.evaluate({}) is False

    def test_predicate_all_true(self):
        p = Predicate(op=PredicateOp.ALL_TRUE, field="checks", value=None)
        assert p.evaluate({"checks": [True, True]}) is True
        assert p.evaluate({"checks": [True, False]}) is False

    def test_predicate_set_contains(self):
        p = Predicate(op=PredicateOp.SET_CONTAINS, field="items", value="a")
        assert p.evaluate({"items": ["a", "b"]}) is True
        assert p.evaluate({"items": ["b", "c"]}) is False

    def test_from_dict_roundtrip(self):
        spec = RequirementSpec(
            id="test.req",
            kind=RequirementKind.EVIDENCE,
            description="test",
            evidence_sources=["file_read"],
            projection="test_proj",
            predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
            blocking=True,
            trace_template="test failed",
        )
        d = spec.to_dict()
        restored = RequirementSpec.from_dict(d)
        assert restored.id == spec.id
        assert restored.predicate.op == spec.predicate.op


class TestEvidenceStore:
    def test_append_and_query(self):
        store = EvidenceStore()
        from bracket.core.events import EvidenceEvent, make_event_id, make_timestamp

        event = EvidenceEvent(
            event_id=make_event_id(),
            run_id="run_test",
            seq=store.next_seq(),
            ts=make_timestamp(),
            event_type=EventType.FILE_READ,
            source_framework="test",
            payload={"path": "app.py", "source": "tool", "byte_count": 100},
        )
        store.append(event)
        assert len(store.events) == 1
        assert store.get_events_by_type(EventType.FILE_READ) == [event]

    def test_compute_summary(self):
        store = EvidenceStore()
        from bracket.core.events import EvidenceEvent, make_event_id, make_timestamp

        for evt_type, payload in [
            (EventType.FILE_READ, {"path": "a.py", "source": "tool", "byte_count": 10}),
            (EventType.FILE_CHANGED, {"path": "a.py", "change_kind": "update", "artifact_ref": ""}),
            (
                EventType.COMMAND_RESULT_RECORDED,
                {"command": "pytest", "exit_code": 0, "stdout_ref": "", "stderr_ref": "", "kind": "verification"},
            ),
        ]:
            store.append(
                EvidenceEvent(
                    event_id=make_event_id(),
                    run_id="run_test",
                    seq=store.next_seq(),
                    ts=make_timestamp(),
                    event_type=evt_type,
                    source_framework="test",
                    payload=payload,
                )
            )

        summary = store.compute_summary()
        assert "a.py" in summary.file_reads
        assert "a.py" in summary.file_changes
        assert summary.verification_commands == 1

    def test_projection_file_read_before_changed(self):
        store = EvidenceStore()
        from bracket.core.events import EvidenceEvent, make_event_id, make_timestamp

        # Read then change = match
        store.append(
            EvidenceEvent(
                event_id=make_event_id(),
                run_id="r",
                seq=store.next_seq(),
                ts=make_timestamp(),
                event_type=EventType.FILE_READ,
                source_framework="t",
                payload={"path": "a.py", "source": "tool", "byte_count": 10},
            )
        )
        store.append(
            EvidenceEvent(
                event_id=make_event_id(),
                run_id="r",
                seq=store.next_seq(),
                ts=make_timestamp(),
                event_type=EventType.FILE_CHANGED,
                source_framework="t",
                payload={"path": "a.py", "change_kind": "update", "artifact_ref": ""},
            )
        )
        # Change without read = violation
        store.append(
            EvidenceEvent(
                event_id=make_event_id(),
                run_id="r",
                seq=store.next_seq(),
                ts=make_timestamp(),
                event_type=EventType.FILE_CHANGED,
                source_framework="t",
                payload={"path": "b.py", "change_kind": "create", "artifact_ref": ""},
            )
        )

        result = store.compute_projection("file_read_before_file_changed")
        assert result["matches"] == 1
        assert "b.py" in result["violations"]


class TestVerdictEngine:
    def test_code_change_verified(self):
        contract = ExecutionContract.code_change(goal="Fix bug")
        store = EvidenceStore()
        from bracket.core.events import EvidenceEvent, make_event_id, make_timestamp

        events = [
            (EventType.RUN_STARTED, {"goal": "Fix bug", "profile_id": "code_change"}),
            (EventType.FILE_READ, {"path": "app.py", "source": "tool", "byte_count": 100}),
            (EventType.FILE_CHANGED, {"path": "app.py", "change_kind": "update", "artifact_ref": ""}),
            (EventType.COMMAND_EXECUTED, {"command": "pytest", "cwd": ".", "kind": "verification"}),
            (
                EventType.COMMAND_RESULT_RECORDED,
                {"command": "pytest", "exit_code": 0, "stdout_ref": "", "stderr_ref": "", "kind": "verification"},
            ),
            (EventType.TOOL_SUCCEEDED, {"tool_name": "edit", "arguments_ref": "", "result_ref": ""}),
            (EventType.RUN_FINISHED, {"final_output": "Fixed the bug."}),
        ]
        for evt_type, payload in events:
            store.append(
                EvidenceEvent(
                    event_id=make_event_id(),
                    run_id="r",
                    seq=store.next_seq(),
                    ts=make_timestamp(),
                    event_type=evt_type,
                    source_framework="test",
                    payload=payload,
                )
            )

        engine = VerdictEngine()
        verdict = engine.evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.VERIFIED
        assert not verdict.missing_requirement_ids

    def test_code_change_blocked_no_verification(self):
        contract = ExecutionContract.code_change(goal="Fix bug")
        store = EvidenceStore()
        from bracket.core.events import EvidenceEvent, make_event_id, make_timestamp

        events = [
            (EventType.RUN_STARTED, {"goal": "Fix bug", "profile_id": "code_change"}),
            (EventType.FILE_READ, {"path": "app.py", "source": "tool", "byte_count": 100}),
            (EventType.FILE_CHANGED, {"path": "app.py", "change_kind": "update", "artifact_ref": ""}),
            (EventType.TOOL_SUCCEEDED, {"tool_name": "edit", "arguments_ref": "", "result_ref": ""}),
            (EventType.RUN_FINISHED, {"final_output": "Done."}),
        ]
        for evt_type, payload in events:
            store.append(
                EvidenceEvent(
                    event_id=make_event_id(),
                    run_id="r",
                    seq=store.next_seq(),
                    ts=make_timestamp(),
                    event_type=evt_type,
                    source_framework="test",
                    payload=payload,
                )
            )

        engine = VerdictEngine()
        verdict = engine.evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.BLOCKED
        assert "evidence.verification.present" in verdict.missing_requirement_ids


class TestHarnessEndToEnd:
    def test_full_code_change_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test-agent", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix test")

            run = harness.start_run(contract)
            run.record_file_read("app.py", byte_count=500)
            run.record_tool_call("file.read", {"path": "app.py"})
            run.record_file_changed("app.py")
            run.record_tool_success("file.write")
            run.record_command("pytest tests/test_app.py", exit_code=0, kind="verification")

            artifact = harness.finish_run_sync(run, final_output="Fixed.")

            assert artifact.verdict.outcome == VerdictOutcome.VERIFIED

            # Verify artifact files were saved
            run_dir = Path(tmp) / "runs" / run.run_id
            assert (run_dir / "contract.json").exists()
            assert (run_dir / "events.jsonl").exists()
            assert (run_dir / "verdict.json").exists()
            assert (run_dir / "replay.json").exists()

            # Verify verdict.json content
            verdict_data = json.loads((run_dir / "verdict.json").read_text())
            assert verdict_data["outcome"] == "verified"

    def test_partial_run_missing_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test-agent", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix test")

            run = harness.start_run(contract)
            # No file read — change without read = violation
            run.record_file_changed("app.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")

            artifact = harness.finish_run_sync(run, final_output="Done.")

            assert artifact.verdict.outcome == VerdictOutcome.BLOCKED
            assert "evidence.read.before_write" in artifact.verdict.missing_requirement_ids
