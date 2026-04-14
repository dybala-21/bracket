"""Replay tests — verify trace_replay recomputes verdict correctly."""

import tempfile

from bracket.core.contracts import ExecutionContract
from bracket.core.harness import Harness
from bracket.core.verdict import VerdictOutcome
from bracket.replay import TraceReplay


class TestTraceReplay:
    def test_replay_matches_original_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test-agent", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix test")

            run = harness.start_run(contract)
            run.record_file_read("app.py", byte_count=500)
            run.record_file_changed("app.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")

            artifact = harness.finish_run_sync(run, final_output="Fixed.")
            assert artifact.verdict.outcome == VerdictOutcome.VERIFIED

            # Replay from saved artifact
            from pathlib import Path

            run_dir = Path(tmp) / "runs" / run.run_id
            replayer = TraceReplay(run_dir)
            replayed_verdict = replayer.replay()

            assert replayed_verdict.outcome == artifact.verdict.outcome
            assert replayed_verdict.missing_requirement_ids == artifact.verdict.missing_requirement_ids
