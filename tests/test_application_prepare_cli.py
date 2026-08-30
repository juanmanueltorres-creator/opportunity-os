from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

import app.application.prepare as prepare_module
from app.application.prepare import main
from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
    Requirement,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-cli-1",
        source="manual",
        source_id="fixture-cli-1",
        source_url="https://example.test/jobs/cli-1",
        company="Example Spatial Labs",
        title="GIS Developer",
        description="Required: PostGIS.",
        discovered_at=NOW,
        published_at=NOW,
        status="found",
        location="Cordoba, Argentina",
        remote_policy="remote",
        required_skills=["PostGIS"],
    )


def _assessment() -> RadarAssessment:
    opportunity = _opportunity()
    requirement = Requirement(
        kind="skill",
        value="PostGIS",
        importance="mandatory",
        exactness="exact_product",
        provenance=DerivedValue(
            value="PostGIS",
            source_text="Required: PostGIS.",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=1.0,
        ),
    )
    enrichment = OpportunityEnrichment(
        opportunity_id=opportunity.id,
        normalized_title=DerivedValue(
            value="GIS Developer",
            source_text="GIS Developer",
            source_field="title",
            extraction_method="explicit_rule",
            confidence=1.0,
        ),
        requirements=[requirement],
        extractor_version="rules-v1",
        taxonomy_versions={},
        created_at=NOW,
    )
    confidence = ConfidenceAssessment(
        score=90,
        requirement_extraction_quality=90,
        skill_normalization_coverage=90,
        evidence_traceability=90,
        seniority_location_legal_clarity=90,
        source_freshness_completeness=90,
    )
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
        best_career_track="tech",
        career_match=88,
        best_income_track="tech",
        income_viability=76,
        confidence_score=90,
        confidence_breakdown=confidence,
        tier="HIGH",
        intent_tiers={"CAREER": "HIGH"},
        priority_score=88.4,
        selected_intent="CAREER",
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
    )


@pytest.fixture
def assessment_path(tmp_path: Path) -> Path:
    path = tmp_path / "radar_assessment.json"
    path.write_text(_assessment().model_dump_json(indent=2), encoding="utf-8")
    return path


@pytest.fixture
def opportunity_only_path(tmp_path: Path) -> Path:
    path = tmp_path / "opportunity.json"
    path.write_text(_opportunity().model_dump_json(indent=2), encoding="utf-8")
    return path


@pytest.fixture
def master_path(tmp_path: Path) -> Path:
    path = tmp_path / "master_facts.local.yaml"
    path.write_text(
        """schema_version: v1
facts:
  - id: identity-name
    kind: identity
    value: Alex Example
    display_values: {en: Alex Example}
    track_ids: [tech]
    verified: true
    verification_method: manual_confirmation
    verified_at: '2026-08-28T12:00:00+00:00'
  - id: contact-email
    kind: contact
    value: alex@example.test
    display_values: {en: alex@example.test}
    track_ids: [tech]
    verified: true
    verification_method: manual_confirmation
    verified_at: '2026-08-28T12:00:00+00:00'
  - id: role-primary
    kind: role
    value: GIS Developer
    display_values: {en: GIS Developer}
    track_ids: [tech]
    verified: true
    verification_method: repository_evidence
    verified_at: '2026-08-28T12:00:00+00:00'
    source_ref: https://example.test/evidence/role
  - id: skill-postgis
    kind: skill
    value: PostGIS
    display_values: {en: PostGIS}
    track_ids: [tech]
    verified: true
    verification_method: repository_evidence
    verified_at: '2026-08-28T12:00:00+00:00'
    source_ref: https://example.test/evidence/postgis
  - id: project-geo
    kind: project
    value: Geo platform project
    display_values: {en: Geo platform project}
    track_ids: [tech]
    verified: true
    verification_method: repository_evidence
    verified_at: '2026-08-28T12:00:00+00:00'
    source_ref: https://example.test/evidence/project
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "evidence_catalog.local.yaml"
    path.write_text(
        """schema_version: v1
modules:
  - id: module-project
    track_ids: [tech]
    label: GIS project evidence
    fact_ids: [project-geo, skill-postgis]
    claims: []
    keywords: [postgis, gis developer]
    source_refs: [https://example.test/evidence/project]
    verified: true
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def policy_path() -> Path:
    return Path("config/recruiter_policy.yaml")


def _args(
    *,
    opportunity_path: Path,
    master_path: Path,
    catalog_path: Path,
    policy_path: Path,
    output_root: Path,
) -> list[str]:
    return [
        "--opportunity",
        str(opportunity_path),
        "--master-facts",
        str(master_path),
        "--evidence-catalog",
        str(catalog_path),
        "--recruiter-policy",
        str(policy_path),
        "--output-root",
        str(output_root),
    ]


def test_cli_prepares_from_serialized_radar_assessment(
    assessment_path: Path,
    master_path: Path,
    catalog_path: Path,
    policy_path: Path,
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = main(
        _args(
            opportunity_path=assessment_path,
            master_path=master_path,
            catalog_path=catalog_path,
            policy_path=policy_path,
            output_root=tmp_path / "applications",
        )
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "PREPARED"
    assert output["page_count"] == 1
    assert len(output["cv_sha256"]) == 64
    assert len(output["packet_sha256"]) == 64
    assert Path(output["cv_pdf_path"]).is_file()
    assert Path(output["cv_pdf_path"]).with_name("application_packet.json").is_file()


def test_cli_removes_recruiter_pdf_when_packet_write_fails(
    assessment_path: Path,
    master_path: Path,
    catalog_path: Path,
    policy_path: Path,
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_root = tmp_path / "applications"

    def fail_packet_write(_result):
        raise OSError("simulated packet write failure")

    monkeypatch.setattr(prepare_module, "_write_packet", fail_packet_write)

    exit_code = main(
        _args(
            opportunity_path=assessment_path,
            master_path=master_path,
            catalog_path=catalog_path,
            policy_path=policy_path,
            output_root=output_root,
        )
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "ERROR"
    assert output["error"] == "application_artifact_write_failed"
    assert list(output_root.rglob("*.pdf")) == []
    assert list(output_root.rglob("application_packet.json")) == []


def test_cli_rejects_plain_opportunity_without_radar_assessment(
    opportunity_only_path: Path,
    master_path: Path,
    catalog_path: Path,
    policy_path: Path,
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = main(
        _args(
            opportunity_path=opportunity_only_path,
            master_path=master_path,
            catalog_path=catalog_path,
            policy_path=policy_path,
            output_root=tmp_path / "applications",
        )
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code != 0
    assert output["error"] == "invalid_radar_assessment"
    assert not (tmp_path / "applications").exists()
