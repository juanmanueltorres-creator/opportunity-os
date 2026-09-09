from __future__ import annotations

from dataclasses import dataclass

from app.cv.models import EvidenceSelection, RequirementSupport
from app.cv.strategy.policy import NarrativePolicy
from app.radar.models import Requirement


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True)
class RankedRequirement:
    requirement: Requirement
    support: RequirementSupport
    score: float

    @property
    def model_key(self) -> tuple[str, str, str]:
        return (
            _normalize(self.requirement.value),
            self.requirement.kind,
            self.requirement.importance,
        )


def rank_supported_requirements(
    *,
    requirements: list[Requirement],
    selection: EvidenceSelection,
    policy: NarrativePolicy,
    priority_requirements: list[str] | tuple[str, ...] = (),
) -> list[RankedRequirement]:
    unsupported = {_normalize(value) for value in selection.unsupported_requirements}
    priorities = {_normalize(value) for value in priority_requirements}
    seen: set[str] = set()
    ranked: list[RankedRequirement] = []

    for requirement in requirements:
        normalized = _normalize(requirement.value)
        if normalized in seen or normalized in unsupported:
            continue
        seen.add(normalized)

        support = selection.requirement_support.get(requirement.value)
        if support is None or support.support_level == "UNKNOWN" or not support.fact_ids:
            continue

        score = (
            policy.requirement_importance_weights[requirement.importance]
            + policy.support_level_weights[support.support_level]
            + (policy.priority_requirement_bonus if normalized in priorities else 0.0)
        )
        ranked.append(
            RankedRequirement(
                requirement=requirement,
                support=support,
                score=score,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            _normalize(item.requirement.value),
            item.requirement.kind,
            item.requirement.importance,
        )
    )
    return ranked
