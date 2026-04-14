"""Google ADK adapter for Bracket.

Provides a tool wrapper and run handler for Google Agent Development
Kit agents. Does not import google.adk at module level.

Example::

    from bracket import Harness, ExecutionContract
    from bracket.adapters.google_adk import BracketADKHandler

    harness = Harness(app_name="my-adk-agent", artifact_dir=".bracket")
    contract = ExecutionContract.research(goal="Find pricing info")

    handler = BracketADKHandler(harness, contract)

    # Wrap tools before passing to ADK Agent
    wrapped_tools = handler.wrap_tools([search_web, read_file])
    agent = Agent(tools=wrapped_tools)

    output = agent.run("Find pricing info")
    artifact = handler.finish(final_output=output)
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any

from bracket.core.artifacts import RunArtifact
from bracket.core.contracts import ExecutionContract
from bracket.core.harness import Harness, RunHandle

_FILE_KEYWORDS = {"file", "read", "write", "save", "load", "open", "path"}
_WEB_KEYWORDS = {"search", "web", "http", "url", "fetch", "browse", "request"}
_SHELL_KEYWORDS = {"shell", "bash", "exec", "terminal", "command", "run_command"}

_VERIFICATION_CMD_PATTERNS = (
    "pytest",
    "unittest",
    "mypy",
    "pyright",
    "ruff check",
    "flake8",
    "eslint",
    "tsc",
    "cargo test",
    "go test",
    "npm test",
    "npm run test",
    "yarn test",
    "pnpm test",
    "jest",
    "mocha",
)


def _classify_command_kind(command: str) -> str:
    lower = command.lower().strip()
    for pat in _VERIFICATION_CMD_PATTERNS:
        if pat in lower:
            return "verification"
    return "inspection"


def _infer_category(name: str) -> str | None:
    lower = name.lower()
    for kw in _FILE_KEYWORDS:
        if kw in lower:
            return "file"
    for kw in _WEB_KEYWORDS:
        if kw in lower:
            return "web"
    for kw in _SHELL_KEYWORDS:
        if kw in lower:
            return "shell"
    return None


class BracketADKHandler:
    """Wraps Google ADK tools with automatic Bracket evidence recording.

    Call wrap_tools() to get instrumented versions of your tool functions,
    then pass them to the ADK Agent. After execution, call finish() to
    compute the verdict.
    """

    def __init__(
        self,
        harness: Harness,
        contract: ExecutionContract,
        probes: list[Any] | None = None,
    ) -> None:
        self._harness = harness
        self._probes = probes
        self._run = harness.start_run(contract)

    @property
    def run(self) -> RunHandle:
        return self._run

    def wrap_tools(self, tools: list[Callable[..., Any]]) -> list[Callable[..., Any]]:
        """Wrap a list of tool functions with evidence recording.

        Returns new callables with the same signatures and metadata.
        Each call records tool_call, tool_success/failure, and infers
        canonical evidence from the tool name.
        """
        return [self._wrap_one(tool) for tool in tools]

    def wrap_tool(self, tool: Callable[..., Any]) -> Callable[..., Any]:
        return self._wrap_one(tool)

    def record_model_called(self, model: str, **kwargs: Any) -> None:
        """Manually record an LLM invocation if not captured automatically."""
        self._run.record_model_called(model=model, **kwargs)

    def finish(
        self,
        final_output: str | None = None,
        probes: list[Any] | None = None,
    ) -> RunArtifact:
        all_probes = probes or self._probes
        return self._harness.finish_run_sync(self._run, final_output=final_output, probes=all_probes)

    def _wrap_one(self, tool: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = getattr(tool, "__name__", str(tool))
        category = _infer_category(tool_name)
        run = self._run

        if asyncio.iscoroutinefunction(tool):

            @functools.wraps(tool)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                call_args = _merge_args(args, kwargs)
                evt = run.record_tool_call(tool_name, arguments=call_args)
                try:
                    result = await tool(*args, **kwargs)
                except Exception:
                    run.record_tool_failure(
                        tool_name,
                        error_kind="runtime_error",
                        correlation_id=evt.correlation_id,
                    )
                    raise
                run.record_tool_success(tool_name, correlation_id=evt.correlation_id)
                _emit_canonical(run, tool_name, category, kwargs, result)
                return result

            return async_wrapper

        @functools.wraps(tool)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            call_args = _merge_args(args, kwargs)
            evt = run.record_tool_call(tool_name, arguments=call_args)
            try:
                result = tool(*args, **kwargs)
            except Exception:
                run.record_tool_failure(
                    tool_name,
                    error_kind="runtime_error",
                    correlation_id=evt.correlation_id,
                )
                raise
            run.record_tool_success(tool_name, correlation_id=evt.correlation_id)
            _emit_canonical(run, tool_name, category, kwargs, result)
            return result

        return sync_wrapper


def _merge_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    if args:
        merged["args"] = list(args)
    if kwargs:
        merged.update(kwargs)
    return merged if merged else None


def _emit_canonical(
    run: RunHandle,
    tool_name: str,
    category: str | None,
    kwargs: dict[str, Any],
    result: Any,
) -> None:
    if category == "file":
        path = kwargs.get("path") or kwargs.get("file_path") or kwargs.get("filename") or ""
        lower = tool_name.lower()
        if "write" in lower or "save" in lower:
            run.record_file_changed(path, change_kind="update")
        else:
            byte_count = len(str(result)) if result else 0
            run.record_file_read(path, byte_count=byte_count)

    elif category == "web":
        url = kwargs.get("url") or kwargs.get("query") or ""
        run.record_web_fetch(url)

    elif category == "shell":
        command = kwargs.get("command") or kwargs.get("cmd") or str(kwargs)
        run.record_command(command, kind=_classify_command_kind(command))


__all__ = ["BracketADKHandler"]
