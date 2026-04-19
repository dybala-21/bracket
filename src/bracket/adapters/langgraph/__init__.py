"""LangGraph adapter for Bracket.

Provides a node wrapper and callback handler for stateful graph
execution. Builds on the LangChain callback handler and adds
graph-level node tracking.

Example::

    from bracket import Harness, ExecutionContract
    from bracket.adapters.langgraph import BracketGraphHandler

    harness = Harness(app_name="my-graph-agent", artifact_dir=".bracket")
    contract = ExecutionContract.code_change(goal="Fix bug")

    handler = BracketGraphHandler(harness, contract)

    # Pass as callback to graph.invoke()
    result = graph.invoke(
        {"input": "fix the bug"},
        config={"callbacks": [handler.callback]},
    )
    artifact = handler.finish(final_output=result.get("output", ""))

Or wrap individual nodes::

    @handler.node("code_writer")
    def write_code(state):
        ...
        return state
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bracket.adapters.langchain import BracketCallbackHandler
from bracket.core.artifacts import RunArtifact
from bracket.core.contracts import ExecutionContract
from bracket.core.harness import Harness, RunHandle
from bracket.replay.llm_recording import LLMRecorder


class BracketGraphHandler:
    """Tracks a LangGraph execution as a single Bracket run.

    Creates a RunHandle on init and provides a callback handler
    for automatic evidence collection. Call finish() after the
    graph completes to get the verdict.
    """

    def __init__(
        self,
        harness: Harness,
        contract: ExecutionContract,
        probes: list[Any] | None = None,
        record_llm: bool = False,
    ) -> None:
        self._harness = harness
        self._probes = probes
        self._run = harness.start_run(contract)
        self._recorder: LLMRecorder | None = LLMRecorder() if record_llm else None
        self._callback = BracketCallbackHandler(self._run, recorder=self._recorder)
        self._node_seq = 0

    @property
    def recorder(self) -> LLMRecorder | None:
        return self._recorder

    @property
    def run(self) -> RunHandle:
        return self._run

    @property
    def callback(self) -> BracketCallbackHandler:
        return self._callback

    def finish(
        self,
        final_output: str | None = None,
        probes: list[Any] | None = None,
    ) -> RunArtifact:
        """Finish the run and compute the verdict.

        Uses probes passed here or the ones supplied to the constructor.
        When constructed with record_llm=True, recorded LLM calls are
        written to llm_calls.json inside the run directory.
        """
        all_probes = probes or self._probes
        artifact = self._harness.finish_run_sync(self._run, final_output=final_output, probes=all_probes)

        if self._recorder is not None and self._recorder.calls:
            run_dir = Path(self._harness.artifact_dir) / "runs" / self._run.run_id
            self._recorder.save(run_dir / "llm_calls.json")

        return artifact

    def node(self, node_name: str) -> Callable[..., Any]:
        """Decorator that wraps a LangGraph node function with evidence tracking.

        Records the node entry and exit as tool_call / tool_success
        events so the execution path is visible in the evidence log.

        Example::

            @handler.node("researcher")
            def researcher(state):
                ...
                return state
        """
        tool_name = f"node:{node_name}"

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if asyncio.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    self._node_seq += 1
                    evt = self._run.record_tool_call(tool_name, arguments={"seq": self._node_seq})
                    try:
                        result = await fn(*args, **kwargs)
                    except Exception:
                        self._run.record_tool_failure(
                            tool_name,
                            error_kind="runtime_error",
                            correlation_id=evt.correlation_id,
                        )
                        raise
                    self._run.record_tool_success(tool_name, correlation_id=evt.correlation_id)
                    return result

                return async_wrapper

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                self._node_seq += 1
                evt = self._run.record_tool_call(tool_name, arguments={"seq": self._node_seq})
                try:
                    result = fn(*args, **kwargs)
                except Exception:
                    self._run.record_tool_failure(
                        tool_name,
                        error_kind="runtime_error",
                        correlation_id=evt.correlation_id,
                    )
                    raise
                self._run.record_tool_success(tool_name, correlation_id=evt.correlation_id)
                return result

            return sync_wrapper

        return decorator


__all__ = ["BracketGraphHandler"]
