"""Tests for the Google ADK adapter -- no google-adk dependency needed."""

import asyncio
import contextlib
import tempfile

from bracket.adapters.google_adk import BracketADKHandler
from bracket.core.contracts import ExecutionContract
from bracket.core.events import EventType
from bracket.core.harness import Harness
from bracket.core.verdict import VerdictOutcome


def search_web(query: str) -> str:
    return f"results for {query}"


def read_file(path: str) -> str:
    return f"contents of {path}"


def write_file(path: str, content: str) -> str:
    return "ok"


def run_shell(command: str) -> str:
    return "ok"


class TestBracketADKHandler:
    def test_wrap_tools_records_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Find info")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tools([search_web, read_file])
            assert len(wrapped) == 2

            result = wrapped[0](query="python docs")
            assert "results for" in result

            called = handler.run.evidence.get_events_by_type(EventType.TOOL_CALLED)
            succeeded = handler.run.evidence.get_events_by_type(EventType.TOOL_SUCCEEDED)
            assert len(called) == 1
            assert len(succeeded) == 1
            assert called[0].correlation_id == succeeded[0].correlation_id

    def test_web_tool_emits_web_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Find info")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tool(search_web)
            wrapped(query="test query")

            fetches = handler.run.evidence.get_events_by_type(EventType.WEB_FETCHED)
            assert len(fetches) == 1

    def test_file_read_emits_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tool(read_file)
            wrapped(path="app.py")

            reads = handler.run.evidence.get_events_by_type(EventType.FILE_READ)
            assert len(reads) == 1
            assert reads[0].payload["path"] == "app.py"

    def test_file_write_emits_file_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.code_change(goal="Fix")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tool(write_file)
            wrapped(path="app.py", content="new code")

            changes = handler.run.evidence.get_events_by_type(EventType.FILE_CHANGED)
            assert len(changes) == 1
            assert changes[0].payload["path"] == "app.py"

    def test_tool_failure_records_error(self):
        def failing_tool():
            raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Test")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tool(failing_tool)
            with contextlib.suppress(RuntimeError):
                wrapped()

            failed = handler.run.evidence.get_events_by_type(EventType.TOOL_FAILED)
            assert len(failed) == 1

    def test_full_research_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Find pricing")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tools([search_web, read_file])
            wrapped[1](path="data.csv")
            wrapped[0](query="pricing info")

            artifact = handler.finish(final_output="Found pricing: $10/mo")
            assert artifact.outcome == VerdictOutcome.VERIFIED

    def test_finish_without_grounding_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Find info")
            handler = BracketADKHandler(harness, contract)

            artifact = handler.finish(final_output="I guessed the answer")
            assert artifact.outcome == VerdictOutcome.BLOCKED

    def test_async_tool_success(self):
        async def async_search(query: str) -> str:
            await asyncio.sleep(0)
            return f"results for {query}"

        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Find info")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tool(async_search)
            result = asyncio.run(wrapped(query="python"))
            assert result == "results for python"

            succeeded = handler.run.evidence.get_events_by_type(EventType.TOOL_SUCCEEDED)
            assert len(succeeded) == 1
            fetches = handler.run.evidence.get_events_by_type(EventType.WEB_FETCHED)
            assert len(fetches) == 1

    def test_async_tool_failure(self):
        async def failing_async():
            await asyncio.sleep(0)
            raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Test")
            handler = BracketADKHandler(harness, contract)

            wrapped = handler.wrap_tool(failing_async)
            with contextlib.suppress(RuntimeError):
                asyncio.run(wrapped())

            failed = handler.run.evidence.get_events_by_type(EventType.TOOL_FAILED)
            assert len(failed) == 1

    def test_record_model_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Harness(app_name="test", artifact_dir=tmp)
            contract = ExecutionContract.research(goal="Find info")
            handler = BracketADKHandler(harness, contract)

            handler.record_model_called("gemini-pro")

            models = handler.run.evidence.get_events_by_type(EventType.MODEL_CALLED)
            assert len(models) == 1
            assert models[0].payload["model"] == "gemini-pro"
