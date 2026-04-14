"""LangChain adapter for Bracket.

Provides a callback handler that automatically translates LangChain
tool and LLM events into canonical Bracket evidence. Requires
``langchain-core`` to be installed.

Example::

    from bracket import Harness, ExecutionContract
    from bracket.adapters.langchain import BracketCallbackHandler

    harness = Harness(app_name="my-agent", artifact_dir=".bracket")
    contract = ExecutionContract.code_change(goal="Fix bug")
    run = harness.start_run(contract)

    handler = BracketCallbackHandler(run)
    agent.invoke(query, config={"callbacks": [handler]})

    result = harness.finish_run_sync(run, final_output=output)
"""

from __future__ import annotations

from typing import Any

from bracket.core.events import EvidenceEvent
from bracket.core.harness import RunHandle

try:
    from langchain_core.callbacks import BaseCallbackHandler as _LCBaseHandler  # type: ignore[import-not-found]

    _LC_AVAILABLE = True
except ImportError:
    _LCBaseHandler = object
    _LC_AVAILABLE = False


_FILE_TOOL_NAMES = frozenset(
    {
        "read_file",
        "file_read",
        "ReadFileTool",
        "write_file",
        "file_write",
        "WriteFileTool",
        "file_search",
        "list_directory",
    }
)

_WEB_TOOL_NAMES = frozenset(
    {
        "web_search",
        "search",
        "tavily_search",
        "TavilySearchResults",
        "requests_get",
        "requests_post",
        "http_request",
        "web_browser",
        "browse_web",
    }
)

_SHELL_TOOL_NAMES = frozenset(
    {
        "terminal",
        "shell",
        "bash",
        "ShellTool",
        "python_repl",
        "python_repl_ast",
        "PythonREPLTool",
    }
)


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
    "rspec",
    "phpunit",
)


def _classify_command_kind(command: str) -> str:
    lower = command.lower().strip()
    for pat in _VERIFICATION_CMD_PATTERNS:
        if pat in lower:
            return "verification"
    if lower.startswith(("ls", "cat", "grep", "find", "pwd", "echo", "which")):
        return "inspection"
    return "inspection"


def _classify_tool(tool_name: str) -> str | None:
    if tool_name in _FILE_TOOL_NAMES:
        return "file"
    if tool_name in _WEB_TOOL_NAMES:
        return "web"
    if tool_name in _SHELL_TOOL_NAMES:
        return "shell"
    lower = tool_name.lower()
    if "file" in lower or "read" in lower or "write" in lower:
        return "file"
    if "search" in lower or "web" in lower or "http" in lower or "url" in lower:
        return "web"
    if "shell" in lower or "bash" in lower or "terminal" in lower or "exec" in lower:
        return "shell"
    return None


class BracketCallbackHandler(_LCBaseHandler):  # type: ignore[misc]
    """LangChain callback handler that records Bracket evidence.

    Inherits from ``langchain_core.callbacks.BaseCallbackHandler`` when
    langchain-core is installed, so the handler is accepted by
    ``Runnable.invoke(config={"callbacks": [handler]})``. When
    langchain-core is not installed, it is a plain class (useful for
    testing the handler in isolation).

    Pass an instance as a callback to agent.invoke() or chain.invoke().
    """

    raise_error: bool = False
    run_inline: bool = False

    def __init__(self, run: RunHandle, recorder: Any = None) -> None:
        if _LC_AVAILABLE:
            super().__init__()
        self._run = run
        self._recorder = recorder
        self._tool_events: dict[str, EvidenceEvent] = {}
        self._tool_context: dict[str, tuple[str, dict[str, Any]]] = {}
        self._llm_starts: dict[str, tuple[str, dict[str, Any]]] = {}

    @staticmethod
    def _extract_model_id(serialized: dict[str, Any]) -> str:
        if "id" in serialized:
            id_parts = serialized["id"]
            if isinstance(id_parts, list) and id_parts:
                return str(id_parts[-1])
        return str(serialized.get("name", "unknown"))

    # LLM callbacks

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        model_id = self._extract_model_id(serialized)
        if self._recorder is not None:
            run_id = str(kwargs.get("run_id", ""))
            self._llm_starts[run_id] = (model_id, {"prompts": list(prompts)})
        self._run.record_model_called(model=model_id)

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list[Any], **kwargs: Any) -> None:
        model_id = self._extract_model_id(serialized)
        if self._recorder is not None:
            run_id = str(kwargs.get("run_id", ""))
            try:
                serialized_msgs = [
                    [
                        {
                            "type": getattr(m, "type", "unknown"),
                            "content": str(getattr(m, "content", "")),
                        }
                        for m in group
                    ]
                    for group in messages
                ]
            except Exception:
                serialized_msgs = [[{"content": str(m)} for m in group] for group in messages]
            self._llm_starts[run_id] = (model_id, {"messages": serialized_msgs})
        self._run.record_model_called(model=model_id)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        if self._recorder is None:
            return
        run_id = str(kwargs.get("run_id", ""))
        if run_id not in self._llm_starts:
            return
        model_id, request = self._llm_starts.pop(run_id)
        response_payload: dict[str, Any]
        try:
            gens = [
                [
                    {
                        "text": getattr(g, "text", ""),
                        "message_content": str(getattr(getattr(g, "message", None), "content", "")),
                    }
                    for g in group
                ]
                for group in response.generations
            ]
            response_payload = {"generations": gens}
        except Exception:
            response_payload = {"text": str(response)}
        self._recorder.record(model=model_id, request=request, response=response_payload)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        if self._recorder is None:
            return
        run_id = str(kwargs.get("run_id", ""))
        self._llm_starts.pop(run_id, None)

    # Tool callbacks

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "unknown")
        run_id = str(kwargs.get("run_id", ""))

        inputs = kwargs.get("inputs")
        if isinstance(inputs, dict):
            tool_input = inputs
        elif isinstance(input_str, str) and input_str:
            tool_input = {"input": input_str}
        else:
            tool_input = {}

        arguments = tool_input if tool_input else None
        evt = self._run.record_tool_call(tool_name, arguments=arguments)
        self._tool_events[run_id] = evt
        self._tool_context[run_id] = (tool_name, tool_input)

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id", ""))

        tool_name, tool_input = self._tool_context.pop(run_id, (kwargs.get("name", "unknown"), {}))
        evt = self._tool_events.pop(run_id, None)
        corr = evt.correlation_id if evt else None

        self._run.record_tool_success(tool_name, correlation_id=corr)
        self._emit_canonical_events(tool_name, tool_input, output)

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id", ""))

        tool_name, _ = self._tool_context.pop(run_id, (kwargs.get("name", "unknown"), {}))
        evt = self._tool_events.pop(run_id, None)
        corr = evt.correlation_id if evt else None

        self._run.record_tool_failure(tool_name, error_kind="runtime_error", correlation_id=corr)

    # Chain callbacks (no-ops, required by protocol)

    def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], **kwargs: Any) -> None:
        pass

    def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        pass

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        pass

    # Canonical evidence inference

    def _emit_canonical_events(self, tool_name: str, tool_input: dict[str, Any], output: Any) -> None:
        category = _classify_tool(tool_name)
        if not isinstance(tool_input, dict):
            tool_input = {}

        if category == "file":
            path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("filename") or ""
            lower = tool_name.lower()
            if "read" in lower or "search" in lower or "list" in lower:
                byte_count = len(str(output)) if output else 0
                self._run.record_file_read(path, byte_count=byte_count)
            elif "write" in lower:
                self._run.record_file_changed(path, change_kind="update")

        elif category == "web":
            url = tool_input.get("url") or tool_input.get("query") or tool_input.get("input") or ""
            self._run.record_web_fetch(url)

        elif category == "shell":
            command = (
                tool_input.get("command") or tool_input.get("input") or tool_input.get("tool_input") or str(tool_input)
            )
            self._run.record_command(command, exit_code=0, kind=_classify_command_kind(command))


__all__ = ["BracketCallbackHandler"]
