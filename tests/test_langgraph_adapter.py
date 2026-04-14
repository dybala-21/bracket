"""Tests for the LangGraph adapter -- no langgraph dependency needed."""

import asyncio
import contextlib
import tempfile

from bracket.adapters.langgraph import BracketGraphHandler
from bracket.core.contracts import ExecutionContract
from bracket.core.events import EventType
from bracket.core.harness import Harness
from bracket.core.verdict import VerdictOutcome


class TestBracketGraphHandler:
    def test_node_decorator_records_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract)

            @handler.node("writer")
            def write_code(state):
                state["code"] = "fixed"
                return state

            result = write_code({"code": ""})
            assert result["code"] == "fixed"

            called = handler.run.evidence.get_events_by_type(EventType.TOOL_CALLED)
            succeeded = handler.run.evidence.get_events_by_type(EventType.TOOL_SUCCEEDED)
            assert len(called) == 1
            assert called[0].payload["tool_name"] == "node:writer"
            assert len(succeeded) == 1
            assert called[0].correlation_id == succeeded[0].correlation_id

    def test_node_failure_records_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract)

            @handler.node("broken")
            def bad_node(state):
                raise ValueError("node failed")

            with contextlib.suppress(ValueError):
                bad_node({})

            failed = handler.run.evidence.get_events_by_type(EventType.TOOL_FAILED)
            assert len(failed) == 1
            assert failed[0].payload["tool_name"] == "node:broken"

    def test_callback_property(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract)

            cb = handler.callback
            cb.on_llm_start({"id": ["ChatOpenAI"]}, ["prompt"])

            model_events = handler.run.evidence.get_events_by_type(EventType.MODEL_CALLED)
            assert len(model_events) == 1

    def test_finish_returns_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract)

            handler.run.record_file_read("a.py", byte_count=10)
            handler.run.record_file_changed("a.py")
            handler.run.record_command("pytest", exit_code=0, kind="verification")
            handler.run.record_tool_success("edit")

            artifact = handler.finish(final_output="Done.")
            assert artifact.outcome == VerdictOutcome.VERIFIED

    def test_async_node_decorator(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract)

            @handler.node("async_writer")
            async def write_code_async(state):
                await asyncio.sleep(0)
                state["code"] = "fixed"
                return state

            result = asyncio.run(write_code_async({"code": ""}))
            assert result["code"] == "fixed"

            called = handler.run.evidence.get_events_by_type(EventType.TOOL_CALLED)
            succeeded = handler.run.evidence.get_events_by_type(EventType.TOOL_SUCCEEDED)
            assert len(called) == 1
            assert len(succeeded) == 1

    def test_record_llm_saves_llm_calls_json(self):
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract, record_llm=True)

            cb = handler.callback
            cb.on_llm_start(
                {"id": ["ChatAnthropic"]},
                ["analyze this code"],
                run_id="lc_run_1",
            )

            class FakeMessage:
                content = "analysis result"

            class FakeGen:
                text = "analysis result"
                message = FakeMessage()

            class FakeResponse:
                def __init__(self) -> None:
                    self.generations = [[FakeGen()]]

            cb.on_llm_end(FakeResponse(), run_id="lc_run_1")

            assert handler.recorder is not None
            assert len(handler.recorder.calls) == 1
            assert handler.recorder.calls[0].model == "ChatAnthropic"
            assert handler.recorder.calls[0].request == {"prompts": ["analyze this code"]}

            handler.run.record_file_read("a.py", byte_count=10)
            handler.run.record_file_changed("a.py")
            handler.run.record_command("pytest", exit_code=0, kind="verification")
            artifact = handler.finish(final_output="Done.")

            llm_calls_path = Path(tmp) / "runs" / artifact.run_id / "llm_calls.json"
            assert llm_calls_path.exists()
            saved = json.loads(llm_calls_path.read_text())
            assert len(saved) == 1
            assert saved[0]["model"] == "ChatAnthropic"

    def test_record_llm_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract)
            assert handler.recorder is None

    def test_multiple_nodes_sequential(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketGraphHandler(harness, contract)

            @handler.node("reader")
            def read_node(state):
                return state

            @handler.node("writer")
            def write_node(state):
                return state

            read_node({})
            write_node({})

            called = handler.run.evidence.get_events_by_type(EventType.TOOL_CALLED)
            assert len(called) == 2
            assert called[0].payload["tool_name"] == "node:reader"
            assert called[1].payload["tool_name"] == "node:writer"
