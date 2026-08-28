from datetime import datetime, timezone

import pytest

from app.cv.models import (
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceModule,
    MasterFact,
    MasterFactsSnapshot,
)
from app.cv.track import (
    CVPreparationError,
    require_minimum_evidence,
    resolve_application_track,
)
from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _confidence() -> ConfidenceAssessment:
    return ConfidenceAssessment(
        score=90,
        requirement_extraction_quality=90,
        skill_normalization_coverage=90,
        evidence_traceability=90,
        seniority_location_legal_clarity=90,
        source_freshness_completeness=90,
    )


def _assessment(
    *,
    selected_intent: str | None,
    best_career_track: str | None,
    best_income_track: str | None,
) -> RadarAssessment:
    opportunity = Opportunity(
        id="opportunity-1",
        source="manual",
        source_id="opportunity-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="Example role",
        description="Example role description",
        discovered_at=NOW,
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=opportunity.id,
        extractor_version="rules-v1",
        created_at=NOW,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
        best_career_track=best_career_track,
        career_match=80 if best_career_track else None,
        best_income_track=best_income_track,
        income_viability=80 if best_income_track else None,
        confidence_score=90,
        confidence_breakdown=_confidence(),
        priority_score=82,
        selected_intent=selected_intent,
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
    )


def _fact(
    fact_id: str,
    kind: str,
    *,
    track_ids: list[str],
    value: str | None = None,
) -> MasterFact:
    method = "manual_confirmation" if kind in {"identity", "contact", "location"} else "repository_evidence"
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value or fact_id,
        track_ids=track_ids,
        verified=True,
        verification_method=method,
        verified_at=NOW,
        source_ref=None if method == "manual_confirmation" else f"https://example.test/{fact_id}",
    )


def _snapshots(
    facts: list[MasterFact],
    modules: list[EvidenceModule],
) -> tuple[MasterFactsSnapshot, EvidenceCatalogSnapshot]:
    return (
        MasterFactsSnapshot(
            schema_version="v1",
            content_sha256="a" * 64,
            facts=facts,
        ),
        EvidenceCatalogSnapshot(
            schema_version="v1",
            content_sha256="b" * 64,
            modules=modules,
        ),
    )


def _policy() -> CVPolicy:
    return CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=["projects"],
        section_order=["summary", "skills", "experience", "projects", "education"],
    )


def test_income_selected_intent_uses_best_income_track() -> None:
    assessment = _assessment(
        selected_intent="INCOME_NOW",
        best_career_track="tech",
        best_income_track="hospitality",
    )

    assert resolve_application_track(assessment) == "hospitality"


def test_missing_selected_lane_falls_back_to_other_winning_track() -> None:
    assessment = _assessment(
        selected_intent="CAREER",
        best_career_track=None,
        best_income_track="tech",
    )

    assert resolve_application_track(assessment) == "tech"


def test_no_winning_track_fails_closed() -> None:
    assessment = _assessment(
        selected_intent="CAREER",
        best_career_track=None,
        best_income_track=None,
    )

    with pytest.raises(CVPreparationError) as exc_info:
        resolve_application_track(assessment)

    assert exc_info.value.code == "track_unavailable"


def test_identity_fact_from_other_track_does_not_satisfy_minimum() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "identity", track_ids=["hospitality"]),
            _fact("email", "contact", track_ids=["tech"]),
            _fact("project", "project", track_ids=["tech"]),
        ],
        [
            EvidenceModule(
                id="module-tech",
                track_ids=["tech"],
                label="Tech project",
                fact_ids=["project"],
                verified=True,
            )
        ],
    )

    with pytest.raises(CVPreparationError) as exc_info:
        require_minimum_evidence("tech", facts, catalog, _policy())

    assert exc_info.value.code == "insufficient_verified_evidence"


def test_module_from_other_track_cannot_make_tech_cv_prepareable() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "identity", track_ids=["tech"]),
            _fact("email", "contact", track_ids=["tech"]),
            _fact("hospitality-employment", "employment", track_ids=["hospitality"]),
        ],
        [
            EvidenceModule(
                id="module-hospitality",
                track_ids=["hospitality"],
                label="Hospitality work",
                fact_ids=["hospitality-employment"],
                verified=True,
            )
        ],
    )

    with pytest.raises(CVPreparationError) as exc_info:
        require_minimum_evidence("tech", facts, catalog, _policy())

    assert exc_info.value.code == "insufficient_verified_evidence"


def test_verified_project_and_required_identity_make_track_prepareable() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "identity", track_ids=["tech"]),
            _fact("email", "contact", track_ids=["tech"]),
            _fact("project", "project", track_ids=["tech"]),
        ],
        [
            EvidenceModule(
                id="module-tech",
                track_ids=["tech"],
                label="Tech project",
                fact_ids=["project"],
                verified=True,
            )
        ],
    )

    require_minimum_evidence("tech", facts, catalog, _policy())


def test_unrelated_posting_gap_is_not_part_of_minimum_evidence_gate() -> None:
    facts, catalog = _snapshots(
        [
            _fact("name", "identity", track_ids=["tech"]),
            _fact("email", "contact", track_ids=["tech"]),
            _fact("project", "project", track_ids=["tech"]),
        ],
        [
            EvidenceModule(
                id="module-tech",
                track_ids=["tech"],
                label="Tech project",
                fact_ids=["project"],
                verified=True,
            )
        ],
    )

    # This gate intentionally receives no posting requirements: unsupported
    # requirements are handled later as unresolved gaps, not invented claims.
    require_minimum_evidence("tech", facts, catalog, _policy())
