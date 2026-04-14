from bracket.core.contracts import ExecutionContract
from bracket.core.events import EventType, EvidenceEvent, make_event_id, make_timestamp
from bracket.core.evidence import EvidenceStore
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


class TestTextAnswerProfile:
    def test_verified_with_grounding(self):
        contract = ExecutionContract.text_answer(goal="Explain X")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Explain X", profile_id="text_answer")
        _make(store, EventType.FILE_READ, path="ref.txt", source="tool", byte_count=50)
        _make(store, EventType.RUN_FINISHED, final_output="X means ...")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.VERIFIED

    def test_blocked_no_grounding(self):
        contract = ExecutionContract.text_answer(goal="Explain X")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Explain X", profile_id="text_answer")
        _make(store, EventType.RUN_FINISHED, final_output="X means ...")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.BLOCKED
        assert "evidence.grounding.present" in verdict.missing_requirement_ids

    def test_blocked_empty_output(self):
        contract = ExecutionContract.text_answer(goal="Explain X")
        store = EvidenceStore()
        _make(store, EventType.RUN_STARTED, goal="Explain X", profile_id="text_answer")
        _make(store, EventType.FILE_READ, path="ref.txt", source="tool", byte_count=50)
        _make(store, EventType.RUN_FINISHED, final_output="")

        verdict = VerdictEngine().evaluate(contract, store)
        assert verdict.outcome == VerdictOutcome.BLOCKED
        assert "outcome.intent_resolved" in verdict.missing_requirement_ids
