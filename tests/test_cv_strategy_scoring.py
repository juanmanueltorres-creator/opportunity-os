from app.cv.models import EvidenceSelection, RequirementSupport
from app.cv.strategy.policy import NarrativePolicy
from app.cv.strategy.scoring import rank_supported_requirements
from app.radar.models import DerivedValue, Requirement


def _policy() -> NarrativePolicy:
    return NarrativePolicy(
        version="narrative-policy-v1",
        max_core_messages=3,
        positioning_message_importance=10.0,
        default_section_order=["summary", "skills", "experience"],
        requirement_importance_weights={
            "mandatory": 3.0,
            "preferred": 2.0,
            "unknown": 1.0,
        },
        support_level_weights={
            "EXACT_VERIFIED": 3.0,
            "APPROVED_ALIAS": 2.5,
            "TAXONOMY_RELATED": 1.0,
            "UNKNOWN": 0.0,
        },
        priority_requirement_bonus=1.0,
    )


def _requirement(value: str, importance: str) -> Requirement:
    return Requirement(
        kind="skill",
        value=value,
        importance=importance,
        exactness="conceptual",
        provenance=DerivedValue[str](
            value=value,
            source_text=f"Required: {value}",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=1.0,
        ),
    )


def _support(value: str, level: str, fact_id: str) -> RequirementSupport:
    return RequirementSupport(
        requirement=value,
        support_level=level,
        fact_ids=[fact_id],
        evidence_ids=[],
        explanation=f"{value} supported by {fact_id}",
    )


def test_mandatory_exact_support_ranks_above_preferred_exact_support() -> None:
    requirements = [
        _requirement("SQL", "preferred"),
        _requirement("Python", "mandatory"),
    ]
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "SQL": _support("SQL", "EXACT_VERIFIED", "skill-sql"),
            "Python": _support("Python", "EXACT_VERIFIED", "skill-python"),
        },
    )

    ranked = rank_supported_requirements(
        requirements=requirements,
        selection=selection,
        policy=_policy(),
    )

    assert [item.requirement.value for item in ranked] == ["Python", "SQL"]


def test_priority_requirement_bonus_breaks_equal_score_deterministically() -> None:
    requirements = [
        _requirement("SQL", "preferred"),
        _requirement("Python", "preferred"),
    ]
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "SQL": _support("SQL", "EXACT_VERIFIED", "skill-sql"),
            "Python": _support("Python", "EXACT_VERIFIED", "skill-python"),
        },
    )

    ranked = rank_supported_requirements(
        requirements=requirements,
        selection=selection,
        policy=_policy(),
        priority_requirements=["SQL"],
    )

    assert [item.requirement.value for item in ranked] == ["SQL", "Python"]


def test_unknown_or_explicit_gap_is_never_ranked_as_supported_message() -> None:
    requirements = [
        _requirement("Power BI", "mandatory"),
        _requirement("PostGIS", "mandatory"),
    ]
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "Power BI": _support("Power BI", "UNKNOWN", "placeholder"),
            "PostGIS": _support("PostGIS", "TAXONOMY_RELATED", "spatial-db"),
        },
        unsupported_requirements=["Power BI", "PostGIS"],
    )

    ranked = rank_supported_requirements(
        requirements=requirements,
        selection=selection,
        policy=_policy(),
    )

    assert ranked == []


def test_ranking_is_independent_of_requirement_input_order() -> None:
    python = _requirement("Python", "mandatory")
    sql = _requirement("SQL", "preferred")
    selection = EvidenceSelection(
        application_track_id="tech",
        requirement_support={
            "Python": _support("Python", "EXACT_VERIFIED", "skill-python"),
            "SQL": _support("SQL", "EXACT_VERIFIED", "skill-sql"),
        },
    )

    first = rank_supported_requirements(
        requirements=[python, sql],
        selection=selection,
        policy=_policy(),
    )
    second = rank_supported_requirements(
        requirements=[sql, python],
        selection=selection,
        policy=_policy(),
    )

    assert [item.model_key for item in first] == [item.model_key for item in second]
