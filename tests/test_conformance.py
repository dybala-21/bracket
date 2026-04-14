"""Conformance kit tests."""

from bracket.adapters.common.conformance import ConformanceChecker
from bracket.core.events import EventType, EvidenceEvent, make_event_id, make_timestamp


class TestConformanceChecker:
    def _make_event(self, seq: int, event_type: EventType, **payload_extra) -> EvidenceEvent:
        return EvidenceEvent(
            event_id=make_event_id(),
            run_id="run_test",
            seq=seq,
            ts=make_timestamp(),
            event_type=event_type,
            source_framework="test",
            payload=payload_extra,
        )

    def test_passing_code_change(self):
        events = [
            self._make_event(1, EventType.RUN_STARTED),
            self._make_event(2, EventType.FILE_READ, path="a.py"),
            self._make_event(3, EventType.FILE_CHANGED, path="a.py"),
            self._make_event(4, EventType.COMMAND_RESULT_RECORDED, kind="verification"),
            self._make_event(5, EventType.RUN_FINISHED),
        ]
        checker = ConformanceChecker()
        report = checker.check(events, "code_change")
        assert report.passed is True

    def test_missing_events(self):
        events = [
            self._make_event(1, EventType.RUN_STARTED),
            self._make_event(2, EventType.RUN_FINISHED),
        ]
        checker = ConformanceChecker()
        report = checker.check(events, "code_change")
        assert report.passed is False
        assert "file_read" in report.missing_events

    def test_seq_violation(self):
        events = [
            self._make_event(5, EventType.RUN_STARTED),
            self._make_event(3, EventType.RUN_FINISHED),  # seq goes backward
        ]
        checker = ConformanceChecker()
        report = checker.check(events, "code_change")
        assert report.passed is False
        assert any(v.rule == "seq_monotonic" for v in report.violations)
