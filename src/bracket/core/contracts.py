from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .policy import RiskLevel
from .requirements import RequirementSpec


class ContractKind(Enum):
    CODE_CHANGE = "code_change"
    RESEARCH = "research"
    FILE_TASK = "file_task"
    TEXT_ANSWER = "text_answer"


@dataclass
class ExecutionContract:
    """Declares what conditions must hold for an execution to be considered complete.

    Use the factory classmethods (code_change, research, file_task,
    text_answer) to create contracts with built-in profile requirements.
    """

    goal: str
    kind: ContractKind
    profile_id: str
    requirement_set_version: str = "1"
    tool_requirement: str | None = None
    requires_verification: bool = False
    requires_grounding: bool = False
    risk_profile: RiskLevel = RiskLevel.LOW
    custom_requirements_ref: str | None = None
    requirements: list[RequirementSpec] = field(default_factory=list)

    @classmethod
    def code_change(
        cls,
        goal: str,
        requires_verification: bool = True,
        risk_profile: RiskLevel = RiskLevel.LOW,
    ) -> ExecutionContract:
        """Create a contract for a code modification task."""
        from .profiles import get_profile_requirements

        return cls(
            goal=goal,
            kind=ContractKind.CODE_CHANGE,
            profile_id="code_change",
            requires_verification=requires_verification,
            risk_profile=risk_profile,
            requirements=get_profile_requirements("code_change"),
        )

    @classmethod
    def research(
        cls,
        goal: str,
        requires_grounding: bool = True,
        risk_profile: RiskLevel = RiskLevel.LOW,
    ) -> ExecutionContract:
        """Create a contract for an information-gathering task."""
        from .profiles import get_profile_requirements

        return cls(
            goal=goal,
            kind=ContractKind.RESEARCH,
            profile_id="research",
            requires_grounding=requires_grounding,
            risk_profile=risk_profile,
            requirements=get_profile_requirements("research"),
        )

    @classmethod
    def file_task(
        cls,
        goal: str,
        risk_profile: RiskLevel = RiskLevel.LOW,
    ) -> ExecutionContract:
        """Create a contract for a file generation task."""
        from .profiles import get_profile_requirements

        return cls(
            goal=goal,
            kind=ContractKind.FILE_TASK,
            profile_id="file_task",
            risk_profile=risk_profile,
            requirements=get_profile_requirements("file_task"),
        )

    @classmethod
    def text_answer(
        cls,
        goal: str,
        requires_grounding: bool = True,
        risk_profile: RiskLevel = RiskLevel.LOW,
    ) -> ExecutionContract:
        """Create a contract for a text response task."""
        from .profiles import get_profile_requirements

        return cls(
            goal=goal,
            kind=ContractKind.TEXT_ANSWER,
            profile_id="text_answer",
            requires_grounding=requires_grounding,
            risk_profile=risk_profile,
            requirements=get_profile_requirements("text_answer"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "kind": self.kind.value,
            "profile_id": self.profile_id,
            "requirement_set_version": self.requirement_set_version,
            "tool_requirement": self.tool_requirement,
            "requires_verification": self.requires_verification,
            "requires_grounding": self.requires_grounding,
            "risk_profile": self.risk_profile.value,
            "custom_requirements_ref": self.custom_requirements_ref,
            "requirements": [r.to_dict() for r in self.requirements],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionContract:
        """profile_id로 built-in requirements를 찾고, 없으면 직렬화된 requirements로 복원."""
        from .profiles import get_profile_requirements

        profile_id = data.get("profile_id", "")
        try:
            requirements = get_profile_requirements(profile_id)
        except Exception:
            requirements = [RequirementSpec.from_dict(r) for r in data.get("requirements", [])]

        risk_raw = data.get("risk_profile")
        risk_profile = RiskLevel(risk_raw) if risk_raw else RiskLevel.LOW

        return cls(
            goal=data["goal"],
            kind=ContractKind(data["kind"]),
            profile_id=profile_id,
            requirement_set_version=data.get("requirement_set_version", "1"),
            tool_requirement=data.get("tool_requirement"),
            requires_verification=data.get("requires_verification", False),
            requires_grounding=data.get("requires_grounding", False),
            risk_profile=risk_profile,
            custom_requirements_ref=data.get("custom_requirements_ref"),
            requirements=requirements,
        )
