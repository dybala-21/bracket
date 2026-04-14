import tempfile

import pytest

from bracket.core.approval import (
    ApprovalBroker,
    AutoApproveHandler,
    AutoDenyHandler,
    Resolution,
)
from bracket.core.contracts import ExecutionContract
from bracket.core.exceptions import BracketError
from bracket.core.harness import Harness
from bracket.core.policy import ActionKind, PolicyDecision, PolicyEngine, PolicyRule, RiskLevel


class TestPolicyEngine:
    def test_file_read_allowed_by_default(self):
        engine = PolicyEngine()
        decision, risk = engine.evaluate(ActionKind.FILE_READ, "app.py")
        assert decision == PolicyDecision.ALLOW
        assert risk == RiskLevel.LOW

    def test_shell_medium_risk_asks(self):
        engine = PolicyEngine()
        decision, risk = engine.evaluate(ActionKind.SHELL, "ls -la")
        assert decision == PolicyDecision.ASK
        assert risk == RiskLevel.MEDIUM

    def test_dangerous_shell_denied(self):
        engine = PolicyEngine()
        decision, risk = engine.evaluate(ActionKind.SHELL, "rm -rf /")
        assert decision == PolicyDecision.DENY
        assert risk == RiskLevel.HIGH

    def test_custom_rule_overrides_default(self):
        rules = [PolicyRule(ActionKind.SHELL, pattern="*", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW)]
        engine = PolicyEngine(rules=rules)
        decision, _risk = engine.evaluate(ActionKind.SHELL, "rm -rf /")
        assert decision == PolicyDecision.ALLOW

    def test_pattern_matching(self):
        rules = [
            PolicyRule(ActionKind.SHELL, pattern="pytest", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW)
        ]
        engine = PolicyEngine(rules=rules)
        decision, _ = engine.evaluate(ActionKind.SHELL, "pytest tests/")
        assert decision == PolicyDecision.ALLOW
        decision, _ = engine.evaluate(ActionKind.SHELL, "ls -la")
        assert decision == PolicyDecision.ASK


class TestPolicyDenyRecordsEvidence:
    def test_deny_emits_approval_resolved_event(self):
        from bracket.core.events import EventType
        from bracket.core.verdict import VerdictOutcome

        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(
                artifact_dir=tmp,
                policy_rules=[
                    PolicyRule(
                        ActionKind.SHELL,
                        pattern="rm -rf",
                        decision=PolicyDecision.DENY,
                        risk_level=RiskLevel.CRITICAL,
                    ),
                ],
            )
            contract = ExecutionContract.code_change(goal="test")
            run = harness.start_run(contract)

            decision = run.check_policy(ActionKind.SHELL, "rm -rf /")
            assert decision == PolicyDecision.DENY

            resolved = run.evidence.get_events_by_type(EventType.APPROVAL_RESOLVED)
            assert len(resolved) == 1
            assert resolved[0].payload["resolution"] == "denied"
            assert resolved[0].payload["resolved_by"] == "policy"
            assert resolved[0].payload["resource"] == "rm -rf /"

            run.record_file_read("a.py", byte_count=1)
            run.record_file_changed("a.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            artifact = harness.finish_run_sync(run, final_output="done")

            assert artifact.verdict.outcome == VerdictOutcome.BLOCKED
            assert any("approval_denied:policy" in f for f in artifact.verdict.hard_failures)


class TestApprovalBroker:
    def test_auto_approve(self):
        broker = ApprovalBroker(handler=AutoApproveHandler())
        seq_counter = iter(range(1, 100))
        result, req_evt, res_evt = broker.request(
            action_kind=ActionKind.SHELL,
            resource="ls",
            risk_level=RiskLevel.MEDIUM,
            run_id="r",
            seq_func=lambda: next(seq_counter),
            source_framework="test",
        )
        assert result.resolution == Resolution.APPROVED
        assert req_evt.seq == 1
        assert res_evt.seq == 2
        assert res_evt.parent_event_id == req_evt.event_id

    def test_auto_deny(self):
        broker = ApprovalBroker(handler=AutoDenyHandler())
        seq_counter = iter(range(1, 100))
        result, _, _ = broker.request(
            action_kind=ActionKind.SHELL,
            resource="rm -rf /",
            risk_level=RiskLevel.HIGH,
            run_id="r",
            seq_func=lambda: next(seq_counter),
            source_framework="test",
        )
        assert result.resolution == Resolution.DENIED

    def test_seq_sync_with_evidence_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="test")
            run = harness.start_run(contract)
            run.record_file_read("a.py", byte_count=1)

            # check_policy triggers approval flow — seqs should be monotonic
            decision = run.check_policy(ActionKind.SHELL, "ls -la")
            assert decision == PolicyDecision.ALLOW

            seqs = [e.seq for e in run.evidence.events]
            for i in range(1, len(seqs)):
                assert seqs[i] > seqs[i - 1], f"seq not monotonic at index {i}: {seqs}"


class TestRunLifecycle:
    def test_record_after_finish_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="test")
            run = harness.start_run(contract)
            run.record_file_read("a.py", byte_count=1)
            run.record_file_changed("a.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")
            harness.finish_run_sync(run, final_output="done")

            with pytest.raises(BracketError):
                run.record_file_read("b.py")

    def test_double_mark_finished_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="test")
            run = harness.start_run(contract)
            run.record_file_read("a.py", byte_count=1)
            run.record_file_changed("a.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")
            run.mark_finished(final_output="done")

            with pytest.raises(BracketError):
                run.mark_finished(final_output="again")


class TestPolicyRuleValidation:
    def test_empty_pattern_rejected(self):
        with pytest.raises(ValueError):
            PolicyRule(ActionKind.SHELL, pattern="", decision=PolicyDecision.DENY)

    def test_wildcard_pattern_allowed(self):
        rule = PolicyRule(ActionKind.SHELL, pattern="*", decision=PolicyDecision.ALLOW)
        engine = PolicyEngine(rules=[rule])
        decision, _ = engine.evaluate(ActionKind.SHELL, "anything")
        assert decision == PolicyDecision.ALLOW
