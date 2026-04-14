from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PolicyDecision(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ActionKind(Enum):
    SHELL = "shell"
    FILE_WRITE = "file_write"
    FILE_READ = "file_read"
    NETWORK = "network"
    TOOL = "tool"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyRule:
    action_kind: ActionKind
    pattern: str
    decision: PolicyDecision
    risk_level: RiskLevel = RiskLevel.LOW

    def __post_init__(self) -> None:
        if not self.pattern:
            raise ValueError("PolicyRule.pattern must be non-empty (use '*' to match all)")


class PolicyEngine:
    """Evaluates actions against policy rules and default risk heuristics.

    Custom rules are checked first in order. If no rule matches, the
    engine falls back to built-in risk assessment based on action kind.
    """

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self._rules = rules or []

    def evaluate(self, action_kind: ActionKind, resource: str) -> tuple[PolicyDecision, RiskLevel]:
        for rule in self._rules:
            if rule.action_kind == action_kind and self._matches(rule.pattern, resource):
                return rule.decision, rule.risk_level

        risk = self._assess_default_risk(action_kind, resource)
        match risk:
            case RiskLevel.LOW:
                return PolicyDecision.ALLOW, risk
            case RiskLevel.MEDIUM:
                return PolicyDecision.ASK, risk
            case RiskLevel.HIGH | RiskLevel.CRITICAL:
                return PolicyDecision.DENY, risk
        return PolicyDecision.ASK, RiskLevel.MEDIUM

    def _matches(self, pattern: str, resource: str) -> bool:
        if pattern == "*":
            return True
        return pattern in resource

    def _assess_default_risk(self, action_kind: ActionKind, resource: str) -> RiskLevel:
        match action_kind:
            case ActionKind.FILE_READ:
                return RiskLevel.LOW
            case ActionKind.SHELL:
                dangerous = ["rm ", "rm -rf", "sudo", "chmod", "mkfs", "dd "]
                if any(d in resource for d in dangerous):
                    return RiskLevel.HIGH
                return RiskLevel.MEDIUM
            case ActionKind.FILE_WRITE:
                return RiskLevel.MEDIUM
            case ActionKind.NETWORK:
                return RiskLevel.MEDIUM
            case ActionKind.TOOL:
                return RiskLevel.LOW
        return RiskLevel.MEDIUM
