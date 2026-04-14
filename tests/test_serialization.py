import tempfile
from pathlib import Path

from bracket.core.artifacts import RunArtifact
from bracket.core.contracts import ExecutionContract
from bracket.core.events import EventType, EvidenceEvent, RedactionInfo
from bracket.core.harness import Harness
from bracket.core.verdict import RequirementTrace, Verdict, VerdictOutcome


class TestEvidenceEventRoundtrip:
    def test_minimal(self):
        event = EvidenceEvent(
            event_id="evt_abc123",
            run_id="run_test",
            seq=1,
            ts="2026-04-09T00:00:00+00:00",
            event_type=EventType.FILE_READ,
            source_framework="test",
            payload={"path": "a.py", "source": "tool", "byte_count": 10},
        )
        d = event.to_dict()
        restored = EvidenceEvent.from_dict(d)
        assert restored.event_id == event.event_id
        assert restored.event_type == event.event_type
        assert restored.payload == event.payload
        assert restored.redaction.applied is False

    def test_full_fields(self):
        event = EvidenceEvent(
            event_id="evt_full",
            run_id="run_test",
            seq=5,
            ts="2026-04-09T00:00:00+00:00",
            event_type=EventType.TOOL_SUCCEEDED,
            source_framework="langgraph",
            payload={"tool_name": "edit", "arguments_ref": "", "result_ref": ""},
            session_id="sess_01",
            thread_id="thread_01",
            correlation_id="corr_01",
            parent_event_id="evt_prev",
            actor="runtime",
            source_span_id="span_01",
            artifact_refs=["ref1", "ref2"],
            redaction=RedactionInfo(applied=True, rules=["mask_secrets"]),
        )
        d = event.to_dict()
        restored = EvidenceEvent.from_dict(d)
        assert restored.session_id == "sess_01"
        assert restored.correlation_id == "corr_01"
        assert restored.redaction.applied is True
        assert restored.artifact_refs == ["ref1", "ref2"]


class TestContractRoundtrip:
    def test_code_change(self):
        contract = ExecutionContract.code_change(goal="Fix bug")
        d = contract.to_dict()
        restored = ExecutionContract.from_dict(d)
        assert restored.goal == contract.goal
        assert restored.kind == contract.kind
        assert restored.profile_id == contract.profile_id
        assert len(restored.requirements) == len(contract.requirements)

    def test_text_answer(self):
        contract = ExecutionContract.text_answer(goal="Explain X")
        d = contract.to_dict()
        restored = ExecutionContract.from_dict(d)
        assert restored.kind == contract.kind
        assert restored.profile_id == "text_answer"


class TestVerdictRoundtrip:
    def test_roundtrip(self):
        verdict = Verdict(
            outcome=VerdictOutcome.BLOCKED,
            missing_requirement_ids=["evidence.read.present"],
            hard_failures=["probe_failed:pytest"],
            requirement_traces=[
                RequirementTrace(
                    requirement_id="evidence.read.present",
                    passed=False,
                    projection_result={"count": 0},
                    message="No file read evidence",
                ),
            ],
            explanation="0/1 requirements passed",
        )
        d = verdict.to_dict()
        restored = Verdict.from_dict(d)
        assert restored.outcome == VerdictOutcome.BLOCKED
        assert restored.missing_requirement_ids == ["evidence.read.present"]
        assert len(restored.requirement_traces) == 1
        assert restored.requirement_traces[0].passed is False


class TestRunArtifactLoadSave:
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test-agent", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix test")
            run = harness.start_run(contract)
            run.record_file_read("app.py", byte_count=100)
            run.record_file_changed("app.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")
            artifact = harness.finish_run_sync(run, final_output="Fixed.")

            run_dir = Path(tmp) / "runs" / run.run_id
            loaded = RunArtifact.load(run_dir)

            assert loaded.verdict.outcome == artifact.verdict.outcome
            assert loaded.verdict.missing_requirement_ids == artifact.verdict.missing_requirement_ids
            assert len(loaded.events) == len(artifact.events)
            assert loaded.metadata == {"app_name": "test-agent"}

    def test_artifact_files_private_permissions(self):
        import stat
        import sys

        if sys.platform == "win32":
            return

        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="x")
            run = harness.start_run(contract)
            run.record_file_read("a.py", byte_count=1)
            run.record_file_changed("a.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")
            harness.finish_run_sync(run, final_output="done")

            run_dir = Path(tmp) / "runs" / run.run_id
            for name in ("contract.json", "events.jsonl", "verdict.json"):
                mode = stat.S_IMODE((run_dir / name).stat().st_mode)
                assert mode == 0o600
