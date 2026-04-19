"""LangChain + Bracket example: research agent (production shape)

Uses langchain.agents.create_agent (the LangChain 1.x recommended
pattern, built on LangGraph internals) to run a real tool-calling
loop against Claude. The agent reads the project README from disk and
fetches a PyPI metadata endpoint, then answers a grounded question.
Bracket collects evidence through its LangChain callback and computes a
verdict against the research profile.

Requires ANTHROPIC_API_KEY. Without the key, the script prints a short
notice and exits 0 so it can sit in a smoke-test matrix unchanged.

Usage:

    pip install bracket-harness[langchain] langchain langchain-anthropic
    export ANTHROPIC_API_KEY=...
    python examples/langchain_research_agent.py
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from bracket import ExecutionContract, Harness, RunArtifact, VerdictOutcome
from bracket.adapters.langchain import BracketCallbackHandler
from bracket.core.policy import ActionKind, PolicyDecision, PolicyRule, RiskLevel
from bracket.probes import FilesystemProbe
from bracket.replay.llm_recording import LLMRecorder

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
PYPI_URL = "https://pypi.org/pypi/bracket-harness/json"
PYPI_URL_FALLBACK = "https://pypi.org/pypi/bracket/json"


def run() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[bracket] ANTHROPIC_API_KEY is not set; skipping agent run.")
        print("[bracket] export the key and re-run, or see tests/ for offline validation.")
        return 0

    from langchain.agents import create_agent
    from langchain_anthropic import ChatAnthropic

    @tool
    def read_local_file(path: str) -> str:
        """Read a UTF-8 text file from the local filesystem and return its content."""
        return Path(path).read_text(encoding="utf-8")

    @tool
    def fetch_url(url: str) -> str:
        """HTTP GET the URL and return the first 4 KB of the response body as text."""
        req = urllib.request.Request(url, headers={"User-Agent": "bracket-example/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(4096).decode("utf-8", errors="replace")

    harness = Harness(
        app_name="research-agent",
        artifact_dir=".bracket",
        source_framework="langchain",
        policy_rules=[
            PolicyRule(ActionKind.FILE_READ, pattern="*", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW),
            PolicyRule(ActionKind.NETWORK, pattern="https://", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW),
        ],
    )
    contract = ExecutionContract.research(
        goal="Explain what Bracket's FilesystemProbe verifies, grounded in the project README and PyPI page.",
    )
    run_handle = harness.start_run(contract)
    recorder = LLMRecorder()
    handler = BracketCallbackHandler(run_handle, recorder=recorder)

    model = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=1024)
    system_prompt = (
        "You are a research assistant. Ground every answer in evidence.\n"
        "Before answering you MUST:\n"
        f"1. Call read_local_file with path='{README_PATH}' to read the project README.\n"
        f"2. Call fetch_url with url='{PYPI_URL}' to get the PyPI metadata. "
        f"If that returns an error, retry with url='{PYPI_URL_FALLBACK}'.\n"
        "Then answer the user's question in 2-3 sentences citing the evidence you collected."
    )
    agent = create_agent(model, tools=[read_local_file, fetch_url], system_prompt=system_prompt)

    question = "What does FilesystemProbe verify, and how does Bracket's 'intent resolved' check relate to it?"

    print(f"[bracket] profile: {contract.profile_id}")
    print(f"[bracket] run_id:  {run_handle.run_id}")
    print(f"[bracket] question: {question}\n")

    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"callbacks": [handler]},
    )
    messages = result.get("messages", [])
    answer = _extract_text(messages[-1].content) if messages else ""

    probes = [FilesystemProbe(str(README_PATH), should_exist=True, contains="FilesystemProbe")]
    artifact = harness.finish_run_sync(run_handle, final_output=answer, probes=probes)

    if recorder.calls:
        run_dir = Path(harness.artifact_dir) / "runs" / run_handle.run_id
        recorder.save(run_dir / "llm_calls.json")

    _print_verdict(artifact, answer, run_handle.run_id)
    return 0 if artifact.verdict.outcome == VerdictOutcome.VERIFIED else 1


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        if parts:
            return "".join(parts)
    return str(content)


def _print_verdict(artifact: RunArtifact, answer: str, run_id: str) -> None:
    v = artifact.verdict
    print(f"[bracket] answer: {answer}\n")
    print(f"[bracket] outcome: {v.outcome.value}")
    print(f"[bracket] reason:  {v.explanation}")
    if v.missing_requirement_ids:
        print(f"[bracket] missing: {v.missing_requirement_ids}")
    if v.hard_failures:
        print(f"[bracket] failures: {v.hard_failures}")
    print()
    for trace in v.requirement_traces:
        print(f"  [{'PASS' if trace.passed else 'FAIL'}] {trace.requirement_id}")
    for pr in artifact.probe_results:
        status = "PASS" if pr.get("passed") else "FAIL"
        print(f"  [probe:{status}] {pr.get('probe_name')}: {pr.get('detail', '')}")
    print(f"\n[bracket] artifacts: .bracket/runs/{run_id}/")


if __name__ == "__main__":
    sys.exit(run())
