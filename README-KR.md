# Bracket

[English](README.md) | 한국어

AI agent가 "다 했어요"라고 말할 때, 진짜 했는지 검증하는 프레임워크.

```
Contract (뭘 해야 하는지) + Evidence (뭘 했는지) = Verdict (진짜 했는지)
```

---

## 문제

LLM 기반 agent는 파일을 읽었다고 하면서 안 읽고, 테스트를 돌렸다고 하면서 안 돌린다.
Agent 프레임워크(LangGraph, Google ADK 등)는 실행은 잘 시켜주지만, 필요한 단계를 실제로 거쳤는지는 검증하지 않는다.

Bracket은 agent의 실행 과정에서 증거를 수집하고, 사전에 정의한 계약 조건과 대조해서 기계적으로 pass/fail을 판정한다.

## 이런 상황에서 쓴다

- Agent가 코드를 수정했다고 하는데, 파일을 읽지도 않고 고쳤는지 확인하고 싶을 때
- Agent 파이프라인에 "테스트 통과 확인" 같은 검증 단계를 끼워넣고 싶을 때
- Agent 실행 로그를 저장해두고 나중에 동일 조건으로 재판정하고 싶을 때
- 여러 agent 프레임워크를 쓰는데, 검증 로직을 하나로 통일하고 싶을 때

## 설치

```bash
pip install bracket-harness
```

import 경로는 `bracket` 그대로 유지된다 (`from bracket import Harness`). Python 3.12+, 코어는 외부 의존성 없음.

## 30초 예제

```python
from bracket import Harness, ExecutionContract

# 1. 계약 정의: "코드를 수정하고 테스트를 통과시켜라"
contract = ExecutionContract.code_change(
    goal="Fix failing test and verify it passes",
)

# 2. 실행 중 증거 수집
harness = Harness(app_name="my-agent", artifact_dir=".bracket")
run = harness.start_run(contract)

run.record_file_read("app.py", byte_count=1842)
run.record_file_changed("app.py")
run.record_command("pytest tests/", exit_code=0, kind="verification")

# 3. 판정
result = harness.finish_run_sync(run, final_output="Fixed the bug.")

print(result.verdict.outcome)            # VerdictOutcome.VERIFIED
print(result.verdict.missing_requirement_ids)  # []
```

`code_change` 계약은 아래 조건을 전부 만족해야 VERIFIED가 된다:

- goal이 final output에서 해소되었는가 (intent resolved)
- 파일을 수정하기 전에 읽었는가 (read-before-write)
- 최소 1개 파일이 변경되었는가
- 최소 1개 커맨드 또는 도구가 실행되었는가
- 검증 커맨드(pytest 등)가 실행되었는가
- hard failure가 없었는가 (tool permission denied, approval denied 등)

하나라도 빠지면 BLOCKED 또는 PARTIAL이 된다. 규칙은 코드로 정의되어 있고, LLM이 판정하지 않는다.

## 구조

```
src/bracket/
  core/           계약, 증거, 판정, 정책, 승인
  probes/         호스트 환경 검증 (파일, 커맨드, HTTP, git, pytest)
  replay/         저장된 로그로 판정 재실행
  adapters/       LangChain, LangGraph, Google ADK 어댑터
```

## 내장 프로파일

| 프로파일 | 핵심 요구사항 |
|---------|-------------|
| `code_change` | read-before-write, file changed, verification command |
| `research` | file read, web fetch, grounding evidence |
| `file_task` | file changed, artifact emitted |
| `text_answer` | grounding evidence |

모든 프로파일에 "intent resolved"와 "hard failure 없음" 조건이 포함된다.

## Probes

Probe는 판정 전에 호스트 환경을 직접 확인한다. agent가 "파일 만들었어요"라고 하면, 진짜 있는지 디스크에서 확인하는 것.

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

| Probe | 검증 대상 |
|-------|---------|
| `FilesystemProbe` | 파일 존재 여부, 내용 포함/미포함 |
| `CommandProbe` | 셸 커맨드 exit code, stdout 내용 |
| `HTTPProbe` | HTTP 응답 status code, body 내용 |
| `GitDiffProbe` | git diff에 특정 파일 포함 여부 |
| `PytestProbe` | pytest 실행 결과 |
| `CustomProbe` | 임의 callable |

Probe가 실패하면 verdict에 hard failure로 반영된다.

## Adapters

기존 agent 프레임워크에 끼워넣는 방식. Agent 코드를 바꾸지 않고 증거를 수집한다.

### LangChain

```python
from bracket.adapters.langchain import BracketCallbackHandler

handler = BracketCallbackHandler(run)
agent.invoke(query, config={"callbacks": [handler]})
```

Callback이 tool 호출을 감지해서 file read, web fetch, shell command 등의 canonical evidence로 자동 변환한다.

### LangGraph

```python
from bracket.adapters.langgraph import BracketGraphHandler

handler = BracketGraphHandler(harness, contract)
result = graph.invoke({"input": "fix the bug"}, config={"callbacks": [handler.callback]})
artifact = handler.finish(final_output=result["output"])
```

개별 노드를 데코레이터로 감쌀 수도 있다:

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

어댑터별 선택 설치:

```bash
pip install bracket-harness[langchain]
pip install bracket-harness[langgraph]
pip install bracket-harness[google-adk]
pip install bracket-harness[all]
```

어댑터가 없는 프레임워크는 `run.record_*` 메서드를 직접 호출하거나 `GenericAdapter`를 쓰면 된다.

## Artifacts

각 실행은 `.bracket/runs/<run_id>/`에 저장된다:

```
contract.json     계약 정의
events.jsonl      실행 중 수집된 canonical event log
summary.json      이벤트 집계
probes.json       probe 실행 결과
verdict.json      최종 판정
replay.json       replay manifest
metadata.json     app name 등 메타데이터
```

전부 JSON이라 다른 도구에서 읽을 수 있다. POSIX 환경에서는 `0600` 권한으로 저장되어 동일 호스트의 다른 사용자로부터 격리된다.

## Replay

저장된 artifact에서 verdict를 재계산한다. 외부 환경을 다시 실행하지 않는다.

```python
from bracket.replay import TraceReplay

verdict = TraceReplay(".bracket/runs/run_20260408_abc123").replay()
```

요구사항 정의가 바뀌었을 때, 과거 실행들을 일괄 재판정하는 데 쓸 수 있다.

LangGraph/LangChain에서 LLM 호출까지 녹화하려면 `record_llm=True`를 주면 된다. finish 시점에 `llm_calls.json`이 run dir에 함께 저장된다.

```python
handler = BracketGraphHandler(harness, contract, record_llm=True)
# ... run graph ...
artifact = handler.finish(final_output=output)
# .bracket/runs/<run_id>/llm_calls.json 에 LLM request/response 저장됨
```

`llm_calls.json`은 프롬프트와 응답을 그대로 저장하므로 민감정보가 포함될 수 있다. 파일은 `0600`으로 저장되고 `.gitignore`에 `.bracket/`이 포함되어 있지만, 백업/CI 로그/공유 호스트로의 유출은 호출자가 관리해야 한다.

## Policy & Approval

위험한 action에 대해 정책 기반 허용/거부/승인 요청을 처리한다.

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

기본 동작: file read는 ALLOW, shell/network/file write는 risk level에 따라 ASK 또는 DENY. `check_policy()`를 호출하면 정책을 평가하고, DENY가 나오면 approval_resolved 이벤트가 evidence에 기록되어 `policy.no_hard_failures` requirement가 감지한다. 즉 DENY 정책을 무시하고 실행해도 verdict는 BLOCKED가 된다.

## Security notes

- Artifact 파일(`.bracket/runs/*`)은 POSIX에서 `0600`으로 저장된다. Windows에서는 OS 기본 ACL을 따른다.
- `FilesystemProbe`의 `contains`/`not_contains` 검사는 파일 앞쪽 10MB까지만 읽는다. `/dev/zero` 등 무한 스트림이나 거대한 파일로 OOM을 유도할 수 없다.
- `PolicyRule`의 `pattern`은 substring 매칭이다. 모든 리소스와 매칭하려면 `"*"`를 쓰고, 빈 문자열은 거부된다.
- `record_llm=True`로 저장되는 `llm_calls.json`은 프롬프트/응답을 평문으로 담는다. 민감정보 redaction과 공유 저장소 접근 제어는 호출자 책임이다.

## Bracket이 아닌 것

- Agent 프레임워크가 아니다 (LangGraph, OpenAI Agents SDK 등을 쓰면 된다)
- Guardrails가 아니다 (입력/출력 필터링이 아니라, 실행 과정 검증이다)
- Observability 도구가 아니다 (로그를 보여주는 게 아니라, pass/fail을 판정한다)
- Eval 플랫폼이 아니다 (응답 품질이 아니라, 실행 완결성을 검증한다)

## License

Apache-2.0
