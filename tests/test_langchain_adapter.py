"""Tests for the LangChain adapter -- no langchain dependency needed."""

import tempfile

from bracket.adapters.langchain import BracketCallbackHandler
from bracket.core.contracts import ExecutionContract
from bracket.core.events import EventType
from bracket.core.harness import Harness
from bracket.core.verdict import VerdictOutcome


class TestBracketCallbackHandler:
    def _make_handler(self):
        tmp = tempfile.mkdtemp()
        harness = Harness(app_name="test", artifact_dir=tmp)
        contract = ExecutionContract.code_change(goal="Fix bug")
        run = harness.start_run(contract)
        handler = BracketCallbackHandler(run)
        return harness, run, handler

    def test_on_llm_start_records_model(self):
        _, run, handler = self._make_handler()
        handler.on_llm_start(
            serialized={"id": ["langchain", "chat_models", "ChatOpenAI"]},
            prompts=["hello"],
        )
        events = run.evidence.get_events_by_type(EventType.MODEL_CALLED)
        assert len(events) == 1
        assert events[0].payload["model"] == "ChatOpenAI"

    def test_on_chat_model_start_records_model(self):
        _, run, handler = self._make_handler()
        handler.on_chat_model_start(
            serialized={"name": "claude-opus"},
            messages=[],
        )
        events = run.evidence.get_events_by_type(EventType.MODEL_CALLED)
        assert len(events) == 1
        assert events[0].payload["model"] == "claude-opus"

    def test_tool_call_success_flow(self):
        _, run, handler = self._make_handler()
        handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str='{"path": "app.py"}',
            run_id="r1",
            inputs={"path": "app.py"},
        )
        handler.on_tool_end(output="file content here", run_id="r1")

        called = run.evidence.get_events_by_type(EventType.TOOL_CALLED)
        succeeded = run.evidence.get_events_by_type(EventType.TOOL_SUCCEEDED)
        assert len(called) == 1
        assert len(succeeded) == 1
        assert called[0].correlation_id == succeeded[0].correlation_id

    def test_tool_call_failure_flow(self):
        _, run, handler = self._make_handler()
        handler.on_tool_start(
            serialized={"name": "write_file"},
            input_str="",
            run_id="r1",
        )
        handler.on_tool_error(
            error=RuntimeError("permission denied"),
            run_id="r1",
        )

        failed = run.evidence.get_events_by_type(EventType.TOOL_FAILED)
        assert len(failed) == 1
        assert failed[0].payload["tool_name"] == "write_file"

    def test_file_read_tool_emits_canonical_event(self):
        _, run, handler = self._make_handler()
        handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str="",
            run_id="r1",
            inputs={"path": "main.py"},
        )
        handler.on_tool_end(output="content", run_id="r1")

        file_reads = run.evidence.get_events_by_type(EventType.FILE_READ)
        assert len(file_reads) == 1
        assert file_reads[0].payload["path"] == "main.py"

    def test_web_search_tool_emits_web_fetch(self):
        _, run, handler = self._make_handler()
        handler.on_tool_start(
            serialized={"name": "web_search"},
            input_str="",
            run_id="r1",
            inputs={"query": "python docs"},
        )
        handler.on_tool_end(output="results", run_id="r1")

        fetches = run.evidence.get_events_by_type(EventType.WEB_FETCHED)
        assert len(fetches) == 1

    def test_shell_tool_emits_command(self):
        _, run, handler = self._make_handler()
        handler.on_tool_start(
            serialized={"name": "terminal"},
            input_str="",
            run_id="r1",
            inputs={"command": "pytest tests/"},
        )
        handler.on_tool_end(output="ok", run_id="r1")

        cmds = run.evidence.get_events_by_type(EventType.COMMAND_EXECUTED)
        assert len(cmds) == 1

        results = run.evidence.get_events_by_type(EventType.COMMAND_RESULT_RECORDED)
        assert len(results) == 1
        assert results[0].payload["kind"] == "verification"

    def test_tool_input_from_input_str_fallback(self):
        _, run, handler = self._make_handler()
        handler.on_tool_start(
            serialized={"name": "custom_tool"},
            input_str="some raw input",
            run_id="r1",
        )
        handler.on_tool_end(output="ok", run_id="r1")

        called = run.evidence.get_events_by_type(EventType.TOOL_CALLED)
        assert len(called) == 1
        assert called[0].payload["arguments"] == {"input": "some raw input"}

    def test_command_classification_avoids_false_positive(self):
        _, run, handler = self._make_handler()
        handler.on_tool_start(
            serialized={"name": "terminal"},
            input_str="",
            run_id="r1",
            inputs={"command": "grep latest file.txt"},
        )
        handler.on_tool_end(output="ok", run_id="r1")

        results = run.evidence.get_events_by_type(EventType.COMMAND_RESULT_RECORDED)
        assert len(results) == 1
        assert results[0].payload["kind"] == "inspection"

    def test_full_code_change_verdict(self):
        harness, run, handler = self._make_handler()

        handler.on_llm_start({"id": ["ChatOpenAI"]}, ["prompt"])
        handler.on_tool_start({"name": "read_file"}, "", run_id="r1", inputs={"path": "app.py"})
        handler.on_tool_end("content", run_id="r1")
        handler.on_tool_start({"name": "write_file"}, "", run_id="r2", inputs={"path": "app.py"})
        handler.on_tool_end("ok", run_id="r2")
        handler.on_tool_start({"name": "terminal"}, "", run_id="r3", inputs={"command": "pytest tests/"})
        handler.on_tool_end("passed", run_id="r3")

        artifact = harness.finish_run_sync(run, final_output="Fixed the bug.")
        assert artifact.outcome == VerdictOutcome.VERIFIED
