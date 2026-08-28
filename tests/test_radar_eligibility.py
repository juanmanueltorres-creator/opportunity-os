from datetime import datetime, timezone

from app.models.domain import CandidateProfile, CandidateTrack, Opportunity
from app.radar.eligibility import evaluate_eligibility
from app.radar.models import DerivedValue, OpportunityEnrichment, Requirement


NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> CandidateProfile:
    data = {
        "name": "Test Candidate",
        "skills": ["Python"],
        "locations": ["Córdoba, Argentina"],
        "target_role_families": ["software"],
    }
    data.update(overrides)
    return CandidateProfile(**data)


def _track(**overrides) -> CandidateTrack:
    data = {
        "id": "income",
        "label": "Income now",
        "intents": ["INCOME_NOW"],
        "skills": ["customer service"],
    }
    data.update(overrides)
    return CandidateTrack(**data)


def _opportunity(**overrides) -> Opportunity:
    data = {
        "id": "manual:1",
        "source": "manual",
        "source_id": "1",
        "source_url": "https://example.com/jobs/1",
        "company": "Example Co",
        "title": "Example Role",
        "description": "Example role description",
        "discovered_at": NOW,
    }
    data.update(overrides)
    return Opportunity(**data)


def _derived(value, *, field: str) -> DerivedValue:
    return DerivedValue(
        value=value,
        source_field=field,
        extraction_method="source_structured",
        confidence=1.0,
    )


def _requirement(kind: str, value: str, *, importance: str = "mandatory") -> Requirement:
    return Requirement(
        kind=kind,
        value=value,
        importance=importance,
        exactness="declarative" if kind in {"license", "work_authorization"} else "conceptual",
        provenance=_derived(value, field="description"),
    )


def _enrichment(**overrides) -> OpportunityEnrichment:
    data = {
        "opportunity_id": "manual:1",
        "extractor_version": "test",
        "created_at": NOW,
    }
    data.update(overrides)
    return OpportunityEnrichment(**data)


def test_role_outside_target_family_is_not_a_hard_fail() -> None:
    result = evaluate_eligibility(
        _opportunity(),
        _enrichment(role_family=_derived("gastronomy", field="role_family")),
        _profile(target_role_families=["software", "data"]),
        _track(),
    )

    assert result.eligible is True
    assert result.hard_fail_reasons == []
    assert "role_outside_target_family" in result.soft_risks


def test_unknown_work_authorization_is_not_a_hard_fail() -> None:
    result = evaluate_eligibility(
        _opportunity(),
        _enrichment(
            requirements=[
                _requirement("work_authorization", "Argentina work authorization")
            ]
        ),
        _profile(work_authorizations=[]),
        _track(),
    )

    assert result.eligible is True
    assert "work_authorization_incompatible" not in result.hard_fail_reasons
    assert "work_authorization_unverified" in result.unknowns


def test_explicit_incompatible_location_is_a_hard_fail() -> None:
    result = evaluate_eligibility(
        _opportunity(location="New York, USA", remote_policy="onsite"),
        _enrichment(),
        _profile(),
        _track(accepted_work_modes=["remote"]),
    )

    assert result.eligible is False
    assert "location_incompatible" in result.hard_fail_reasons


def test_verified_missing_mandatory_license_is_a_hard_fail() -> None:
    result = evaluate_eligibility(
        _opportunity(),
        _enrichment(requirements=[_requirement("license", "Professional License C")]),
        _profile(verified_licenses=["Driver License B"]),
        _track(),
    )

    assert result.eligible is False
    assert "mandatory_license_missing" in result.hard_fail_reasons


def test_unconfigured_license_data_stays_unknown() -> None:
    result = evaluate_eligibility(
        _opportunity(),
        _enrichment(requirements=[_requirement("license", "Professional License C")]),
        _profile(verified_licenses=[]),
        _track(),
    )

    assert result.eligible is True
    assert "mandatory_license_unverified" in result.unknowns


def test_configured_no_go_schedule_is_a_hard_fail() -> None:
    result = evaluate_eligibility(
        _opportunity(),
        _enrichment(work_schedule=_derived("14x14 rotation", field="work_schedule")),
        _profile(no_go_constraints=["14x14"]),
        _track(),
    )

    assert result.eligible is False
    assert "schedule_no_go" in result.hard_fail_reasons


def test_explicit_work_authorization_conflict_is_a_hard_fail() -> None:
    result = evaluate_eligibility(
        _opportunity(),
        _enrichment(
            requirements=[_requirement("work_authorization", "US work authorization")]
        ),
        _profile(work_authorizations=["Argentina work authorization"]),
        _track(),
    )

    assert result.eligible is False
    assert "work_authorization_incompatible" in result.hard_fail_reasons


def test_closed_posting_is_a_hard_fail() -> None:
    result = evaluate_eligibility(
        _opportunity(status="closed"),
        _enrichment(),
        _profile(),
        _track(),
    )

    assert result.eligible is False
    assert "posting_closed" in result.hard_fail_reasons
