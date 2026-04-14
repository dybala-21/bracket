import tempfile

from bracket.core.contracts import ExecutionContract
from bracket.core.events import EventType, EvidenceEvent, make_event_id, make_timestamp
from bracket.core.evidence import EvidenceStore
from bracket.core.exceptions import EvidenceError
from bracket.core.verdict import VerdictEngine, VerdictOutcome


def _make(store, event_type, **payload):
    store.append(
        EvidenceEvent(
            event_id=make_event_id(),
            run_id="r",
            seq=store.next_seq(),
            ts=make_timestamp(),
            event_type=event_type,
            source_framework="test",
            payload=payload,
        )
    )


class TestResearchProfile:
    def test_verified(self):
        contract = ExecutionContract.research(goal="Find info")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Find info", profile_id="research")
        _make(store, EventType.FILE_READ, path="data.txt", source="tool", byte_count=100)
        _make(store, EventType.WEB_FETCHED, url="https://example.com", method="GET", status_code=200, content_ref="")
        _make(store, EventType.RUN_FINISHED, final_output="Found the answer.")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.VERIFIED

    def test_blocked_no_web(self):
        contract = ExecutionContract.research(goal="Find info")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Find info", profile_id="research")
        _make(store, EventType.FILE_READ, path="data.txt", source="tool", byte_count=100)
        _make(store, EventType.RUN_FINISHED, final_output="Guessed the answer.")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.BLOCKED
        assert "evidence.web.present" in verdict.missing_requirement_ids


class TestFileTaskProfile:
    def test_verified(self):
        contract = ExecutionContract.file_task(goal="Generate report")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Generate report", profile_id="file_task")
        _make(store, EventType.FILE_CHANGED, path="report.pdf", change_kind="create", artifact_ref="ref")
        _make(store, EventType.ARTIFACT_EMITTED, artifact_id="report", ref="report.pdf", kind="file")
        _make(store, EventType.RUN_FINISHED, final_output="Report generated.")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.VERIFIED

    def test_blocked_no_artifact(self):
        contract = ExecutionContract.file_task(goal="Generate report")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Generate report", profile_id="file_task")
        _make(store, EventType.FILE_CHANGED, path="report.pdf", change_kind="create", artifact_ref="ref")
        _make(store, EventType.RUN_FINISHED, final_output="Done.")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.BLOCKED
        assert "outcome.file_artifact.present" in verdict.missing_requirement_ids


class TestEdgeCases:
    def test_empty_final_output_fails_intent(self):
        contract = ExecutionContract.code_change(goal="Fix bug")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Fix bug", profile_id="code_change")
        _make(store, EventType.FILE_READ, path="a.py", source="tool", byte_count=10)
        _make(store, EventType.FILE_CHANGED, path="a.py", change_kind="update", artifact_ref="")
        _make(store, EventType.COMMAND_EXECUTED, command="pytest", cwd=".", kind="verification")
        _make(
            store,
            EventType.COMMAND_RESULT_RECORDED,
            command="pytest",
            exit_code=0,
            stdout_ref="",
            stderr_ref="",
            kind="verification",
        )
        _make(store, EventType.TOOL_SUCCEEDED, tool_name="edit", arguments_ref="", result_ref="")
        _make(store, EventType.RUN_FINISHED, final_output="")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.BLOCKED
        assert "outcome.intent_resolved" in verdict.missing_requirement_ids

    def test_unknown_projection_raises(self):
        import pytest

        store = EvidenceStore()
        with pytest.raises(EvidenceError, match="Unknown projection"):
            store.compute_projection("nonexistent")

    def test_run_id_contains_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = __import__("bracket").Harness(artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="test")
            run = harness.start_run(contract)
            import re

            assert re.match(r"run_\d{8}_[a-f0-9]{8}", run.run_id), f"Unexpected run_id format: {run.run_id}"
