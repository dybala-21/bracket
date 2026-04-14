"""LangGraph + Bracket example: code fix agent

A code fix pipeline built with LangGraph StateGraph,
verified with Bracket harness for execution assurance.

Graph:

    analyze -> plan -> implement -> verify -> pass -> done
                           ^                  fail -> implement (retry)

What Bracket records here:
- File reads (analyze node, via record_file_read)
- File changes (implement node, via record_file_changed)
- Artifacts (implement node, via record_artifact)
- Verification commands (verify node, via record_command)
- Policy enforcement (verify node, via check_policy)
- LLM calls (auto-captured via callback when record_llm=True)

Output artifacts (.bracket/runs/<run_id>/):
- contract.json, events.jsonl, summary.json, probes.json
- verdict.json, replay.json, metadata.json
- llm_calls.json (when record_llm=True)

Usage:

    pip install bracket[langgraph] langchain-anthropic
    export ANTHROPIC_API_KEY=...
    python examples/langgraph_code_fix_agent.py

Dry run (no LLM):

    python examples/langgraph_code_fix_agent.py --dry-run
"""

from __future__ import annotations

import operator
import sys
from typing import Annotated, Any, TypedDict

from bracket import ExecutionContract, Harness, VerdictOutcome
from bracket.adapters.langgraph import BracketGraphHandler
from bracket.core.policy import ActionKind, PolicyDecision, PolicyRule, RiskLevel
from bracket.probes import CommandProbe, FilesystemProbe

# State


class AgentState(TypedDict, total=False):
    task: str
    target_file: str
    file_content: str
    analysis: str
    plan: str
    patch: str
    test_result: str
    test_passed: bool
    retry_count: Annotated[int, operator.add]
    final_output: str


MAX_RETRIES = 2


# Harness & Contract


def build_harness() -> Harness:
    return Harness(
        app_name="code-fix-agent",
        artifact_dir=".bracket",
        source_framework="langgraph",
        policy_rules=[
            PolicyRule(ActionKind.SHELL, pattern="pytest", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW),
            PolicyRule(ActionKind.SHELL, pattern="ruff", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW),
            PolicyRule(ActionKind.FILE_READ, pattern="*", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW),
            PolicyRule(ActionKind.SHELL, pattern="rm -rf", decision=PolicyDecision.DENY, risk_level=RiskLevel.CRITICAL),
        ],
    )


def build_contract(task: str) -> ExecutionContract:
    return ExecutionContract.code_change(
        goal=task,
        requires_verification=True,
    )


# Nodes (dry-run: stub data, no LLM)


def make_nodes_dry_run(handler: BracketGraphHandler) -> dict[str, Any]:

    @handler.node("analyze")
    def analyze(state: AgentState) -> AgentState:
        target = state.get("target_file", "app.py")
        content = f"# simulated content of {target}\ndef broken_function():\n    return 1 / 0\n"

        handler.run.record_file_read(target, byte_count=len(content))

        return {
            "file_content": content,
            "analysis": "ZeroDivisionError in broken_function",
        }

    @handler.node("plan")
    def plan(state: AgentState) -> AgentState:
        return {
            "plan": "Replace return 1 / 0 with return 0 in broken_function",
        }

    @handler.node("implement")
    def implement(state: AgentState) -> AgentState:
        target = state.get("target_file", "app.py")
        patch = "def broken_function():\n    return 0\n"

        handler.run.record_file_changed(target, change_kind="update")
        handler.run.record_artifact(artifact_id=f"patch_{target}", ref=target, kind="file")

        return {"patch": patch}

    @handler.node("verify")
    def verify(state: AgentState) -> AgentState:
        command = "pytest tests/ -x"

        decision = handler.run.check_policy(ActionKind.SHELL, command)
        if decision == PolicyDecision.DENY:
            return {"test_result": "blocked by policy", "test_passed": False, "retry_count": 1}

        handler.run.record_command(command, exit_code=0, kind="verification")

        return {
            "test_result": "1 passed",
            "test_passed": True,
            "retry_count": 0,
        }

    @handler.node("done")
    def done(state: AgentState) -> AgentState:
        target = state.get("target_file", "app.py")
        return {
            "final_output": f"Fixed {target}. Tests pass.",
        }

    return {
        "analyze": analyze,
        "plan": plan,
        "implement": implement,
        "verify": verify,
        "done": done,
    }


# Nodes (LLM: actual Anthropic calls)


def make_nodes_llm(handler: BracketGraphHandler) -> dict[str, Any]:
    from langchain_anthropic import ChatAnthropic

    # ChatAnthropic accepts LangChain callbacks via config in each .invoke() call,
    # but when the graph is invoked with config={"callbacks": [handler.callback]},
    # the callback propagates to child runnables automatically. So model/LLM
    # events are recorded without any explicit record_model_called in nodes.
    llm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=1024)

    @handler.node("analyze")
    def analyze(state: AgentState) -> AgentState:
        target = state.get("target_file", "app.py")

        try:
            with open(target) as f:
                content = f.read()
        except FileNotFoundError:
            content = ""

        handler.run.record_file_read(target, byte_count=len(content))

        resp = llm.invoke(
            f"Analyze the code below and explain any bugs.\n\n```python\n{content}\n```\n\nTask: {state['task']}"
        )

        return {
            "file_content": content,
            "analysis": resp.content,
        }

    @handler.node("plan")
    def plan(state: AgentState) -> AgentState:
        resp = llm.invoke(f"Analysis: {state['analysis']}\n\nWrite a one-paragraph fix plan.")

        return {"plan": resp.content}

    @handler.node("implement")
    def implement(state: AgentState) -> AgentState:
        target = state.get("target_file", "app.py")

        resp = llm.invoke(
            f"Fix the file below. Output only the code block.\n\n"
            f"Current code:\n```python\n{state['file_content']}\n```\n\n"
            f"Fix plan: {state['plan']}"
        )

        patch = resp.content
        handler.run.record_file_changed(target, change_kind="update")
        handler.run.record_artifact(artifact_id=f"patch_{target}", ref=target, kind="file")

        return {"patch": patch}

    @handler.node("verify")
    def verify(state: AgentState) -> AgentState:
        import subprocess

        command = "pytest tests/ -x"
        decision = handler.run.check_policy(ActionKind.SHELL, command)
        if decision == PolicyDecision.DENY:
            return {
                "test_result": "blocked by policy",
                "test_passed": False,
                "retry_count": 1,
            }

        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-x", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        passed = result.returncode == 0
        handler.run.record_command(
            command,
            exit_code=result.returncode,
            kind="verification",
        )

        return {
            "test_result": result.stdout[-500:] if result.stdout else result.stderr[-500:],
            "test_passed": passed,
            "retry_count": 1,
        }

    @handler.node("done")
    def done(state: AgentState) -> AgentState:
        target = state.get("target_file", "app.py")
        return {
            "final_output": f"Fixed {target}. Tests pass.",
        }

    return {
        "analyze": analyze,
        "plan": plan,
        "implement": implement,
        "verify": verify,
        "done": done,
    }


# Graph assembly


def build_graph(nodes: dict[str, Any]) -> Any:
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)

    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "plan")
    graph.add_edge("plan", "implement")
    graph.add_edge("implement", "verify")

    def should_retry(state: AgentState) -> str:
        if state.get("test_passed"):
            return "done"
        if state.get("retry_count", 0) >= MAX_RETRIES:
            return "done"
        return "implement"

    graph.add_conditional_edges("verify", should_retry, {"done": "done", "implement": "implement"})
    graph.add_edge("done", END)

    return graph.compile()


# Run


def run(dry_run: bool = False) -> None:
    task = "Fix the broken_function bug and verify tests pass"
    target_file = "app.py"

    harness = build_harness()
    contract = build_contract(task)

    probes = []
    if not dry_run:
        probes = [
            FilesystemProbe(target_file),
            CommandProbe("python -m pytest tests/ -x", expected_exit_code=0, timeout=30),
        ]

    # record_llm=True turns on LLM request/response capture via the callback.
    # Only effective when handler.callback is propagated to LLM invocations
    # (done below via graph.invoke config).
    handler = BracketGraphHandler(
        harness,
        contract,
        probes=probes,
        record_llm=not dry_run,
    )

    nodes = make_nodes_dry_run(handler) if dry_run else make_nodes_llm(handler)

    app = build_graph(nodes)

    print(f"[bracket] contract: {contract.profile_id}")
    print(f"[bracket] run_id:   {handler.run.run_id}")
    print(f"[bracket] goal:     {task}")
    print()

    # Passing handler.callback to graph.invoke propagates it to every child
    # runnable (LLMs, tools), so LLM request/response pairs are recorded
    # automatically when record_llm=True.
    result = app.invoke(
        {
            "task": task,
            "target_file": target_file,
            "retry_count": 0,
        },
        config={"callbacks": [handler.callback]},
    )

    final_output = result.get("final_output", "")
    artifact = handler.finish(final_output=final_output)

    v = artifact.verdict
    print(f"[bracket] outcome:  {v.outcome.value}")
    print(f"[bracket] explanation: {v.explanation}")

    if v.missing_requirement_ids:
        print(f"[bracket] missing:  {v.missing_requirement_ids}")

    if v.hard_failures:
        print(f"[bracket] failures: {v.hard_failures}")

    print()
    for trace in v.requirement_traces:
        status = "PASS" if trace.passed else "FAIL"
        print(f"  [{status}] {trace.requirement_id}")

    print(f"\n[bracket] artifacts saved: .bracket/runs/{handler.run.run_id}/")
    if handler.recorder is not None and handler.recorder.calls:
        print(f"[bracket] llm calls recorded: {len(handler.recorder.calls)} -> llm_calls.json")

    if v.outcome != VerdictOutcome.VERIFIED:
        print("\n[bracket] verdict: NOT VERIFIED")
        sys.exit(1)
    else:
        print("\n[bracket] verdict: VERIFIED")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
