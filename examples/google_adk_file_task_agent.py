"""Google ADK + Bracket example: file task agent (production shape)

Uses google.adk.agents.LlmAgent + Runner to run a real tool-calling loop
against Gemini. The agent reads a template file, fills placeholders,
and writes the filled report back to disk. Bracket wraps the tools so
every call becomes canonical evidence, then judges the run against the
file_task profile.

Requires GOOGLE_API_KEY (Gemini API) or GOOGLE_APPLICATION_CREDENTIALS
(Vertex AI). Without credentials, the script prints a notice and exits 0.

Usage:

    pip install bracket-harness[google-adk]
    export GOOGLE_API_KEY=...
    python examples/google_adk_file_task_agent.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from bracket import ExecutionContract, Harness, RunArtifact, VerdictOutcome
from bracket.adapters.google_adk import BracketADKHandler
from bracket.probes import FilesystemProbe

TEMPLATE_BODY = "# Weekly report\n\nUptime: [UPTIME]\nIncidents: [INCIDENTS]\n\n## Status: [STATUS]\n"
REPORT_MARKER = "## Status:"


async def run_agent(
    handler: BracketADKHandler,
    template_path: Path,
    output_path: Path,
) -> str:
    def read_template(path: str) -> str:
        """Read the report template from the given path and return the content."""
        return Path(path).read_text(encoding="utf-8")

    def write_report(path: str, content: str) -> str:
        """Write the filled report to the given path. Overwrites if it exists."""
        Path(path).write_text(content, encoding="utf-8")
        return f"wrote {len(content)} bytes to {path}"

    wrapped = handler.wrap_tools([read_template, write_report])

    agent = LlmAgent(
        name="report_agent",
        model="gemini-2.5-flash",
        description="Fills a weekly status report template and writes it to disk.",
        instruction=(
            f"Produce a report file at {output_path}.\n"
            f"Step 1: call read_template with path='{template_path}'.\n"
            "Step 2: in the returned text, replace [UPTIME] with 99.97%, "
            "[INCIDENTS] with none, and [STATUS] with ok.\n"
            f"Step 3: call write_report with path='{output_path}' and the filled content.\n"
            "Step 4: reply with one line confirming the path you wrote."
        ),
        tools=wrapped,
    )

    app_name = "report-agent"
    user_id = "ci-user"
    session_id = "session-1"

    session_service = InMemorySessionService()
    await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    message = types.Content(role="user", parts=[types.Part(text="Generate this week's status report.")])

    final_text = ""
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""
    return final_text


def run() -> int:
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")):
        print("[bracket] GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS is not set; skipping agent run.")
        print("[bracket] export credentials and re-run, or see tests/ for offline validation.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        template_path = Path(tmp) / "template.md"
        output_path = Path(tmp) / "report.md"
        template_path.write_text(TEMPLATE_BODY, encoding="utf-8")

        harness = Harness(
            app_name="report-agent",
            artifact_dir=".bracket",
            source_framework="google-adk",
        )
        contract = ExecutionContract.file_task(goal="Generate this week's status report from the template.")
        handler = BracketADKHandler(harness, contract)

        print(f"[bracket] profile: {contract.profile_id}")
        print(f"[bracket] run_id:  {handler.run.run_id}\n")

        final_text = asyncio.run(run_agent(handler, template_path, output_path))

        if output_path.exists():
            # file_task profile requires both file_changed (recorded by the wrapped
            # write_report tool) and artifact_emitted (explicit, below).
            handler.run.record_artifact(artifact_id=f"report-{output_path.name}", ref=str(output_path), kind="file")

        probes = [FilesystemProbe(str(output_path), should_exist=True, contains=REPORT_MARKER)]
        artifact = handler.finish(final_output=final_text, probes=probes)

        _print_verdict(artifact, final_text, handler.run.run_id)
        return 0 if artifact.verdict.outcome == VerdictOutcome.VERIFIED else 1


def _print_verdict(artifact: RunArtifact, final_text: str, run_id: str) -> None:
    v = artifact.verdict
    print(f"[bracket] final: {final_text}")
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
