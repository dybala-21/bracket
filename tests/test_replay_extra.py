import tempfile
from pathlib import Path

from bracket.core.contracts import ExecutionContract
from bracket.core.exceptions import ReplayError
from bracket.core.harness import Harness
from bracket.replay import LLMCall, LLMPlayback, LLMRecorder, ToolStubReplay


class TestLLMRecorder:
    def test_record_and_save_load(self, tmp_path):
        recorder = LLMRecorder()
        recorder.record(
            model="claude-opus-4-6",
            request={"messages": [{"role": "user", "content": "hello"}]},
            response={"content": "hi"},
            duration_ms=150,
        )
        recorder.record(
            model="claude-opus-4-6",
            request={"messages": [{"role": "user", "content": "bye"}]},
            response={"content": "goodbye"},
        )

        assert len(recorder.calls) == 2
        assert recorder.calls[0].seq == 1
        assert recorder.calls[1].seq == 2

        path = tmp_path / "llm.json"
        recorder.save(path)
        loaded = LLMRecorder.load(path)
        assert len(loaded) == 2
        assert loaded[0].model == "claude-opus-4-6"
        assert loaded[1].response == {"content": "goodbye"}


class TestLLMPlayback:
    def test_playback_sequence(self):
        calls = [
            LLMCall(seq=1, model="m", request={}, response={"r": 1}),
            LLMCall(seq=2, model="m", request={}, response={"r": 2}),
        ]
        playback = LLMPlayback(calls)
        assert playback.remaining == 2
        assert not playback.exhausted

        assert playback.next_response() == {"r": 1}
        assert playback.remaining == 1

        assert playback.next_response() == {"r": 2}
        assert playback.exhausted

    def test_raises_replay_error_when_exhausted(self):
        import pytest

        playback = LLMPlayback([])
        with pytest.raises(ReplayError):
            playback.next_response()


class TestToolStubReplay:
    def test_load_stubs_from_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            run = harness.start_run(contract)
            call_evt = run.record_tool_call("file.read", {"path": "a.py"})
            run.record_tool_success("file.read", correlation_id=call_evt.correlation_id)
            run.record_file_read("a.py", byte_count=10)
            run.record_file_changed("a.py")
            run.record_command("pytest", exit_code=0, kind="verification")
            harness.finish_run_sync(run, final_output="Done.")

            run_dir = Path(tmp) / "runs" / run.run_id
            stub_replay = ToolStubReplay(run_dir)
            stubs = stub_replay.load_tool_stubs()
            assert len(stubs) > 0
