from __future__ import annotations

from .exceptions import ContractError
from .requirements import Predicate, PredicateOp, RequirementKind, RequirementSpec

_CODE_CHANGE_REQUIREMENTS = [
    RequirementSpec(
        id="outcome.intent_resolved",
        kind=RequirementKind.OUTCOME,
        description="The stated goal must be addressed in final output",
        evidence_sources=["run_finished"],
        projection="intent_resolved",
        predicate=Predicate(op=PredicateOp.EXISTS, field="resolved", value=True),
        blocking=True,
        trace_template="Run finished without resolving intent: {goal}",
    ),
    RequirementSpec(
        id="evidence.read.before_write",
        kind=RequirementKind.EVIDENCE,
        description="A file must be read before it is modified",
        evidence_sources=["file_read", "file_changed"],
        projection="file_read_before_file_changed",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="matches", value=1),
        blocking=True,
        trace_template="file {path} changed without prior read evidence",
    ),
    RequirementSpec(
        id="evidence.write.present",
        kind=RequirementKind.EVIDENCE,
        description="At least one file change must be recorded",
        evidence_sources=["file_changed"],
        projection="file_changed_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No file changes recorded",
    ),
    RequirementSpec(
        id="evidence.execution.present",
        kind=RequirementKind.EVIDENCE,
        description="At least one command or tool execution must be recorded",
        evidence_sources=["command_executed", "tool_succeeded"],
        projection="execution_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No execution evidence recorded",
    ),
    RequirementSpec(
        id="evidence.verification.present",
        kind=RequirementKind.EVIDENCE,
        description="At least one verification command must be recorded",
        evidence_sources=["command_result_recorded"],
        projection="verification_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No verification evidence recorded",
    ),
    RequirementSpec(
        id="policy.no_hard_failures",
        kind=RequirementKind.POLICY,
        description="No hard policy failures occurred during the run",
        evidence_sources=["tool_failed", "approval_resolved"],
        projection="hard_failure_count",
        predicate=Predicate(op=PredicateOp.COUNT_EQ, field="count", value=0),
        blocking=True,
        trace_template="Hard policy failure detected",
    ),
]

_RESEARCH_REQUIREMENTS = [
    RequirementSpec(
        id="outcome.intent_resolved",
        kind=RequirementKind.OUTCOME,
        description="The stated goal must be addressed in final output",
        evidence_sources=["run_finished"],
        projection="intent_resolved",
        predicate=Predicate(op=PredicateOp.EXISTS, field="resolved", value=True),
        blocking=True,
        trace_template="Run finished without resolving intent: {goal}",
    ),
    RequirementSpec(
        id="evidence.read.present",
        kind=RequirementKind.EVIDENCE,
        description="At least one file read must be recorded",
        evidence_sources=["file_read"],
        projection="file_read_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No file read evidence recorded",
    ),
    RequirementSpec(
        id="evidence.grounding.present",
        kind=RequirementKind.EVIDENCE,
        description="Grounding evidence must be present",
        evidence_sources=["file_read", "web_fetched", "command_result_recorded"],
        projection="grounding_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No grounding evidence recorded",
    ),
    RequirementSpec(
        id="evidence.web.present",
        kind=RequirementKind.EVIDENCE,
        description="At least one web fetch must be recorded",
        evidence_sources=["web_fetched"],
        projection="web_fetch_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No web fetch evidence recorded",
    ),
    RequirementSpec(
        id="policy.no_hard_failures",
        kind=RequirementKind.POLICY,
        description="No hard policy failures occurred during the run",
        evidence_sources=["tool_failed", "approval_resolved"],
        projection="hard_failure_count",
        predicate=Predicate(op=PredicateOp.COUNT_EQ, field="count", value=0),
        blocking=True,
        trace_template="Hard policy failure detected",
    ),
]

_FILE_TASK_REQUIREMENTS = [
    RequirementSpec(
        id="outcome.intent_resolved",
        kind=RequirementKind.OUTCOME,
        description="The stated goal must be addressed in final output",
        evidence_sources=["run_finished"],
        projection="intent_resolved",
        predicate=Predicate(op=PredicateOp.EXISTS, field="resolved", value=True),
        blocking=True,
        trace_template="Run finished without resolving intent: {goal}",
    ),
    RequirementSpec(
        id="evidence.write.present",
        kind=RequirementKind.EVIDENCE,
        description="At least one file change must be recorded",
        evidence_sources=["file_changed"],
        projection="file_changed_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No file changes recorded",
    ),
    RequirementSpec(
        id="outcome.file_artifact.present",
        kind=RequirementKind.OUTCOME,
        description="File artifact must be emitted",
        evidence_sources=["artifact_emitted"],
        projection="file_artifact_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No file artifact emitted",
    ),
    RequirementSpec(
        id="policy.no_hard_failures",
        kind=RequirementKind.POLICY,
        description="No hard policy failures occurred during the run",
        evidence_sources=["tool_failed", "approval_resolved"],
        projection="hard_failure_count",
        predicate=Predicate(op=PredicateOp.COUNT_EQ, field="count", value=0),
        blocking=True,
        trace_template="Hard policy failure detected",
    ),
]

_TEXT_ANSWER_REQUIREMENTS = [
    RequirementSpec(
        id="outcome.intent_resolved",
        kind=RequirementKind.OUTCOME,
        description="The stated goal must be addressed in final output",
        evidence_sources=["run_finished"],
        projection="intent_resolved",
        predicate=Predicate(op=PredicateOp.EXISTS, field="resolved", value=True),
        blocking=True,
        trace_template="Run finished without resolving intent: {goal}",
    ),
    RequirementSpec(
        id="evidence.grounding.present",
        kind=RequirementKind.EVIDENCE,
        description="Grounding evidence must be present",
        evidence_sources=["file_read", "web_fetched", "command_result_recorded"],
        projection="grounding_count",
        predicate=Predicate(op=PredicateOp.COUNT_GTE, field="count", value=1),
        blocking=True,
        trace_template="No grounding evidence recorded",
    ),
    RequirementSpec(
        id="policy.no_hard_failures",
        kind=RequirementKind.POLICY,
        description="No hard policy failures occurred during the run",
        evidence_sources=["tool_failed", "approval_resolved"],
        projection="hard_failure_count",
        predicate=Predicate(op=PredicateOp.COUNT_EQ, field="count", value=0),
        blocking=True,
        trace_template="Hard policy failure detected",
    ),
]

_PROFILES: dict[str, list[RequirementSpec]] = {
    "code_change": _CODE_CHANGE_REQUIREMENTS,
    "research": _RESEARCH_REQUIREMENTS,
    "file_task": _FILE_TASK_REQUIREMENTS,
    "text_answer": _TEXT_ANSWER_REQUIREMENTS,
}


def get_profile_requirements(profile_id: str) -> list[RequirementSpec]:
    """Return a copy of the built-in requirements for a profile.

    Raises ContractError if profile_id is not recognized. Available
    profiles: 'code_change', 'research', 'file_task', 'text_answer'.
    """
    if profile_id not in _PROFILES:
        raise ContractError(f"Unknown profile: {profile_id}")
    return list(_PROFILES[profile_id])
