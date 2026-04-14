# Bracket

English | [한국어](README-KR.md)

A framework for verifying that AI agents actually did what they claim when they say "done."

```
Contract (what to do) + Evidence (what was done) = Verdict (was it really done)
```

---

## Problem

LLM-based agents claim to read files without reading them, and claim to run tests without running them.
Agent frameworks (LangGraph, Google ADK, etc.) are good at executing, but they do not verify that the required steps actually happened.

Bracket collects evidence during an agent's execution and mechanically decides pass/fail against a pre-defined contract.

## When to use it

- When an agent claims to have modified code, and you want to confirm it didn't patch a file it never read.
- When you want to plug a verification step like "tests passed" into an agent pipeline.
- When you want to persist agent execution logs and re-judge them later under the same conditions.
- When you use multiple agent frameworks and want a single verification layer across them.

## Install

```bash
pip install bracket
```

Python 3.12+. No external dependencies.

## 30-second example

```python
from bracket import Harness, ExecutionContract

# 1. Define the contract: "modify code and make the tests pass"
contract = ExecutionContract.code_change(
    goal="Fix failing test and verify it passes",
)

# 2. Collect evidence during execution
harness = Harness(app_name="my-agent", artifact_dir=".bracket")
run = harness.start_run(contract)

run.record_file_read("app.py", byte_count=1842)
run.record_file_changed("app.py")
run.record_command("pytest tests/", exit_code=0, kind="verification")

# 3. Judge
result = harness.finish_run_sync(run, final_output="Fixed the bug.")

print(result.verdict.outcome)            # VerdictOutcome.VERIFIED
print(result.verdict.missing_requirement_ids)  # []
```

The `code_change` contract is VERIFIED only when all of the following hold:

- The goal is resolved in the final output (intent resolved)
- The file was read before it was modified (read-before-write)
- At least one file was changed
- At least one command or tool was executed
- A verification command (pytest, etc.) was executed
- No hard failures occurred (tool permission denied, approval denied, etc.)

If any of these is missing, the outcome becomes BLOCKED or PARTIAL. The rules are defined in code; no LLM judges the result.

## Layout

```
src/bracket/
  core/           contracts, evidence, verdict, policy, approval
  probes/         host-side verification (file, command, HTTP, git, pytest)
  replay/         re-run the verdict from saved logs
  adapters/       LangChain, LangGraph, Google ADK adapters
```

## Built-in profiles

| Profile | Core requirements |
|---------|-------------------|
| `code_change` | read-before-write, file changed, verification command |
| `research` | file read, web fetch, grounding evidence |
| `file_task` | file changed, artifact emitted |
| `text_answer` | grounding evidence |

Every profile includes "intent resolved" and "no hard failure" conditions.

## Probes

A probe checks the host environment directly before the verdict is computed. When an agent says "I created the file," a probe actually checks the disk.

```python
from bracket.probes import PytestProbe, FilesystemProbe

result = harness.finish_run_sync(
    run,
    final_output="Done.",
    probes=[
        PytestProbe("tests/"),
        FilesystemProbe("output.json", contains='"status": "ok"'),
    ],
)
```

| Probe | Verifies |
|-------|----------|
| `FilesystemProbe` | File existence, contains / does-not-contain |
| `CommandProbe` | Shell command exit code, stdout contents |
| `HTTPProbe` | HTTP response status, body contents |
| `GitDiffProbe` | Whether specific files appear in git diff |
| `PytestProbe` | pytest run result |
| `CustomProbe` | Arbitrary callable |

A failing probe is recorded as a hard failure in the verdict.

## Adapters

Drop-in integrations for existing agent frameworks. Evidence is collected without modifying agent code.

### LangChain

```python
from bracket.adapters.langchain import BracketCallbackHandler

handler = BracketCallbackHandler(run)
agent.invoke(query, config={"callbacks": [handler]})
```

The callback observes tool calls and converts them to canonical evidence like file reads, web fetches, and shell commands.

### LangGraph

```python
from bracket.adapters.langgraph import BracketGraphHandler

handler = BracketGraphHandler(harness, contract)
result = graph.invoke({"input": "fix the bug"}, config={"callbacks": [handler.callback]})
artifact = handler.finish(final_output=result["output"])
```

Individual nodes can also be wrapped with a decorator:

```python
@handler.node("code_writer")
def write_code(state):
    ...
    return state
```

### Google ADK

```python
from bracket.adapters.google_adk import BracketADKHandler

handler = BracketADKHandler(harness, contract)
wrapped_tools = handler.wrap_tools([search_web, read_file])
```

Optional installs per adapter:

```bash
pip install bracket[langchain]
pip install bracket[langgraph]
pip install bracket[google-adk]
pip install bracket[all]
```

For frameworks without an adapter, call `run.record_*` methods directly or use `GenericAdapter`.

## Artifacts

Each run is stored under `.bracket/runs/<run_id>/`:

```
contract.json     contract definition
events.jsonl      canonical event log collected during execution
summary.json      event aggregates
probes.json       probe results
verdict.json      final verdict
replay.json       replay manifest
metadata.json     metadata such as app name
```

Everything is JSON, so other tools can read it. On POSIX, files are stored with `0600` permissions so they are isolated from other users on the same host.

## Replay

Recomputes a verdict from a saved artifact. The external environment is not re-executed.

```python
from bracket.replay import TraceReplay

verdict = TraceReplay(".bracket/runs/run_20260408_abc123").replay()
```

Useful for re-judging past runs in bulk when the requirement definitions change.

To also record LLM calls in LangGraph/LangChain, pass `record_llm=True`. On finish, `llm_calls.json` is written next to the other artifacts.

```python
handler = BracketGraphHandler(harness, contract, record_llm=True)
# ... run graph ...
artifact = handler.finish(final_output=output)
# .bracket/runs/<run_id>/llm_calls.json holds the LLM request/response pairs
```

`llm_calls.json` stores prompts and responses verbatim, so it may contain sensitive data. The file is written with `0600` permissions and `.bracket/` is in `.gitignore`, but leaks via backups, CI logs, or shared hosts are the caller's responsibility.

## Policy & Approval

Risky actions are gated by a policy that allows, asks, or denies.

```python
from bracket import Harness
from bracket.core.policy import PolicyRule, PolicyDecision, ActionKind, RiskLevel

harness = Harness(
    app_name="my-agent",
    artifact_dir=".bracket",
    policy_rules=[
        PolicyRule(ActionKind.SHELL, pattern="pytest", decision=PolicyDecision.ALLOW, risk_level=RiskLevel.LOW),
    ],
)
```

Defaults: file reads are ALLOW; shell, network, and file writes are ASK or DENY depending on risk level. Calling `check_policy()` evaluates the policy, and a DENY emits an `approval_resolved` event into the evidence stream, which the `policy.no_hard_failures` requirement detects. So even if the agent ignores the DENY and proceeds, the verdict becomes BLOCKED.

## Security notes

- Artifact files (`.bracket/runs/*`) are stored with `0600` on POSIX. On Windows they inherit the OS default ACL.
- `FilesystemProbe`'s `contains` / `not_contains` check reads only the first 10 MB of the file. An infinite stream like `/dev/zero` or a very large file cannot induce OOM.
- `PolicyRule.pattern` uses substring matching. Use `"*"` to match all resources; the empty string is rejected.
- `llm_calls.json` written by `record_llm=True` holds prompts and responses in plaintext. Redacting sensitive data and controlling access to shared storage are the caller's responsibility.

## What Bracket is not

- Not an agent framework (use LangGraph, OpenAI Agents SDK, etc. for that).
- Not guardrails (not input/output filtering, but execution verification).
- Not an observability tool (does not show logs, it decides pass/fail).
- Not an eval platform (not about response quality, but about execution completeness).

## License

Apache-2.0
