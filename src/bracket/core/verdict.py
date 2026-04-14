from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .contracts import ExecutionContract
from .evidence import EvidenceStore


class VerdictOutcome(Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    BLOCKED = "blocked"


@dataclass
class RequirementTrace:
    requirement_id: str
    passed: bool
    projection_result: dict[str, Any]
    message: str


@dataclass
class Verdict:
    outcome: VerdictOutcome
    missing_requirement_ids: list[str] = field(default_factory=list)
    hard_failures: list[str] = field(default_factory=list)
    requirement_traces: list[RequirementTrace] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "missing_requirement_ids": self.missing_requirement_ids,
            "hard_failures": self.hard_failures,
            "requirement_traces": [
                {
                    "requirement_id": t.requirement_id,
                    "passed": t.passed,
                    "projection_result": t.projection_result,
                    "message": t.message,
                }
                for t in self.requirement_traces
            ],
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Verdict:
        traces = [
            RequirementTrace(
                requirement_id=t["requirement_id"],
                passed=t["passed"],
                projection_result=t["projection_result"],
                message=t["message"],
            )
            for t in data.get("requirement_traces", [])
        ]
        return cls(
            outcome=VerdictOutcome(data["outcome"]),
            missing_requirement_ids=data.get("missing_requirement_ids", []),
            hard_failures=data.get("hard_failures", []),
            requirement_traces=traces,
            explanation=data.get("explanation", ""),
        )


class VerdictEngine:
    """Evaluates a contract against collected evidence to produce a verdict.

    The engine computes projections for each requirement, applies typed
    predicates, and combines the results with probe outcomes and hard
    failures to determine the final outcome.
    """

    def evaluate(
        self,
        contract: ExecutionContract,
        evidence: EvidenceStore,
        probe_results: list[dict[str, Any]] | None = None,
    ) -> Verdict:
        """Evaluate all requirements and return a Verdict.

        Returns VERIFIED if all pass, PARTIAL if only non-blocking
        requirements fail, BLOCKED if any blocking requirement fails
        or hard failures are present.
        """
        missing: list[str] = []
        traces: list[RequirementTrace] = []
        has_blocking_failure = False

        for req in contract.requirements:
            projection_result = evidence.compute_projection(req.projection)
            passed = req.predicate.evaluate(projection_result)

            traces.append(
                RequirementTrace(
                    requirement_id=req.id,
                    passed=passed,
                    projection_result=projection_result,
                    message="" if passed else req.trace_template,
                )
            )

            if not passed:
                missing.append(req.id)
                if req.blocking:
                    has_blocking_failure = True

        probe_failures: list[str] = []
        if probe_results:
            for pr in probe_results:
                if not pr.get("passed", False):
                    probe_failures.append(pr.get("probe_name", "unknown"))

        summary = evidence.compute_summary()
        hard_failures = summary.hard_failures + [f"probe_failed:{name}" for name in probe_failures]

        if hard_failures or has_blocking_failure:
            outcome = VerdictOutcome.BLOCKED
        elif missing:
            outcome = VerdictOutcome.PARTIAL
        else:
            outcome = VerdictOutcome.VERIFIED

        passed_count = sum(1 for t in traces if t.passed)
        total_count = len(traces)
        explanation = f"{passed_count}/{total_count} requirements passed"
        if missing:
            explanation += f"; missing: {', '.join(missing)}"
        if hard_failures:
            explanation += f"; hard failures: {', '.join(hard_failures)}"

        return Verdict(
            outcome=outcome,
            missing_requirement_ids=missing,
            hard_failures=hard_failures,
            requirement_traces=traces,
            explanation=explanation,
        )
