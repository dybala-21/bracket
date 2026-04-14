import tempfile

from bracket.adapters import GenericAdapter, LifecycleHook
from bracket.core.contracts import ExecutionContract
from bracket.core.harness import Harness
from bracket.core.verdict import VerdictOutcome


class TestGenericAdapter:
    def test_wrap_and_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            adapter = GenericAdapter(harness)

            assert adapter.framework_name == "generic"

            contract = ExecutionContract.code_change(goal="Fix bug")
            run = adapter.wrap_run(contract)

            run.record_file_read("a.py", byte_count=10)
            run.record_file_changed("a.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")

            result = adapter.finalize_run(run, final_output="Fixed.")
            assert result.verdict.outcome == VerdictOutcome.VERIFIED


class TestLifecycleHook:
    def test_fire_callbacks(self):
        hook = LifecycleHook()
        log = []

        hook.on_run_start(lambda **kw: log.append(("start", kw)))
        hook.on_run_end(lambda **kw: log.append(("end", kw)))

        hook.fire_run_start(run_id="r1")
        hook.fire_run_end(run_id="r1", outcome="verified")

        assert len(log) == 2
        assert log[0] == ("start", {"run_id": "r1"})
        assert log[1] == ("end", {"run_id": "r1", "outcome": "verified"})


class TestHarnessLifecycleCallbacks:
    def test_callbacks_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            log = []
            harness.on_run_start(lambda **kw: log.append("start"))
            harness.on_run_end(lambda **kw: log.append("end"))

            contract = ExecutionContract.code_change(goal="Fix")
            run = harness.start_run(contract)
            run.record_file_read("a.py", byte_count=10)
            run.record_file_changed("a.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            run.record_tool_success("edit")
            harness.finish_run_sync(run, final_output="Done.")

            assert log == ["start", "end"]
