from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RequirementKind(Enum):
    EVIDENCE = "evidence"
    PROBE = "probe"
    POLICY = "policy"
    OUTCOME = "outcome"


class PredicateOp(Enum):
    COUNT_GTE = "count_gte"
    COUNT_EQ = "count_eq"
    EXISTS = "exists"
    ALL_TRUE = "all_true"
    ANY_TRUE = "any_true"
    SET_CONTAINS = "set_contains"
    ENUM_EQ = "enum_eq"


@dataclass(frozen=True)
class Predicate:
    """A typed evaluator applied to a projection result.

    Combines an operator, a field name to extract from the projection
    dict, and an expected value.
    """

    op: PredicateOp
    field: str
    value: Any

    def evaluate(self, projection_result: dict[str, Any]) -> bool:
        actual = projection_result.get(self.field)
        match self.op:
            case PredicateOp.COUNT_GTE:
                return isinstance(actual, (int, float)) and actual >= self.value
            case PredicateOp.COUNT_EQ:
                return isinstance(actual, (int, float)) and actual == self.value
            case PredicateOp.EXISTS:
                return actual is not None and bool(actual)
            case PredicateOp.ALL_TRUE:
                return isinstance(actual, list) and len(actual) > 0 and all(actual)
            case PredicateOp.ANY_TRUE:
                return isinstance(actual, list) and any(actual)
            case PredicateOp.SET_CONTAINS:
                return isinstance(actual, (set, list)) and self.value in actual
            case PredicateOp.ENUM_EQ:
                return bool(actual == self.value)
        return False


@dataclass(frozen=True)
class RequirementSpec:
    """A machine-evaluable requirement within an execution contract.

    Each spec names a projection to compute from the evidence store
    and a predicate to apply to the projection result. The verdict
    engine uses these to determine pass/fail per requirement.
    """

    id: str
    kind: RequirementKind
    description: str
    evidence_sources: list[str]
    projection: str
    predicate: Predicate
    blocking: bool
    trace_template: str
    version: str = "1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequirementSpec:
        pred_data = data["predicate"]
        predicate = Predicate(
            op=PredicateOp(pred_data["op"]),
            field=pred_data["field"],
            value=pred_data["value"],
        )
        return cls(
            id=data["id"],
            kind=RequirementKind(data["kind"]),
            description=data["description"],
            evidence_sources=data["evidence_sources"],
            projection=data["projection"],
            predicate=predicate,
            blocking=data["blocking"],
            trace_template=data["trace_template"],
            version=data.get("version", "1"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "description": self.description,
            "evidence_sources": self.evidence_sources,
            "projection": self.projection,
            "predicate": {
                "op": self.predicate.op.value,
                "field": self.predicate.field,
                "value": self.predicate.value,
            },
            "blocking": self.blocking,
            "trace_template": self.trace_template,
            "version": self.version,
        }
