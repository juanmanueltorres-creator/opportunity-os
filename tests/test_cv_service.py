from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.cv.hashing import canonical_sha256
from app.cv.models import (
    CVPolicy,
    EvidenceCatalogSnapshot,
    EvidenceModule,
    MasterFact,
    MasterFactsSnapshot,
    ValidationIssue,
    ValidationResult,
)
from app.cv.renderer import ATSRenderer
from app.cv.service import CVPreparationService
from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
    Requirement,
)
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _resolver() -> TaxonomyResolver:
    return TaxonomyResolver(
        alias_registry=AliasRegistry(version="aliases-v1", entries=()),
    )


def _confidence() -> ConfidenceAssessment:
    return ConfidenceAssessment(
        score=90,
        requirement_extraction_quality=90,
        skill_normalization_coverage=90,
        evidence_traceability=90,
        seniority_location_legal_clarity=90,
        source_freshness_completeness=90,
    )


def _assessment(*, with_track: bool = True) -> RadarAssessment:
    opportunity = Opportunity(
        id="opp-1",
        source="manual",
        source_id="fixture-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="GIS Developer",
        description="Required: PostGIS.",
        discovered_at=NOW,
        published_at=NOW,
        status="found",
        location="Cordoba, Argentina",
        remote_policy="remote",
        required_skills=["PostGIS"],
    )
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
        taxonomy_versions={"esco": "1.2.1"},
        created_at=NOW,
    )
    track = "tech" if with_track else None
    return RadarAssessment(
        opportunity=opportunity,
        enrichment=enrichment,
        eligibility=EligibilityResult(eligible=True),
        best_career_track=track,
        career_match=88 if track else None,
        best_income_track=track,
        income_viability=76 if track else None,
        confidence_score=90,
        confidence_breakdown=_confidence(),
        priority_score=88.4,
        selected_intent="CAREER",
        scoring_version="v0.2a1",
        extractor_version="rules-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={"esco": "1.2.1"},
    )


def _fact(
    fact_id: str,
    kind: str,
    value: str,
    *,
    source_ref: str | None = None,
) -> MasterFact:
    method = (
        "manual_confirmation"
        if kind in {"identity", "contact", "location"}
        else "repository_evidence"
    )
    return MasterFact(
        id=fact_id,
        kind=kind,
        value=value,
        display_values={"en": value},
        track_ids=["tech"],
        verified=True,
        verification_method=method,
        verified_at=NOW,
        source_ref=(
            None
            if method == "manual_confirmation"
            else source_ref or f"https://example.test/evidence/{fact_id}"
        ),
    )


def _inputs(*, project_value: str = "Geo platform project", minimum: bool = True):
    facts = [
        _fact("identity-name", "identity", "Alex Example"),
        _fact("contact-email", "contact", "alex@example.test"),
    ]
    modules: list[EvidenceModule] = []
    if minimum:
        facts.extend(
            [
                _fact("skill-postgis", "skill", "PostGIS"),
                _fact("project-geo", "project", project_value),
            ]
        )
        modules.append(
            EvidenceModule(
                id="module-project",
                track_ids=["tech"],
                label="GIS project evidence",
                fact_ids=["project-geo", "skill-postgis"],
                claims=[],
                keywords=["postgis", "gis developer"],
                source_refs=["https://example.test/evidence/project"],
                verified=True,
            )
        )

    semantic_facts = [fact.model_dump(mode="json") for fact in facts]
    semantic_modules = [module.model_dump(mode="json") for module in modules]
    master = MasterFactsSnapshot(
        schema_version="v1",
        content_sha256=canonical_sha256(semantic_facts),
        facts=facts,
    )
    catalog = EvidenceCatalogSnapshot(
        schema_version="v1",
        content_sha256=canonical_sha256(semantic_modules),
        modules=modules,
    )
    policy = CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=["projects", "skills"],
        section_order=["summary", "skills", "experience", "projects", "education"],
    )
    return master, catalog, policy


def _service(application_id: str = "app-1", renderer=None) -> CVPreparationService:
    return CVPreparationService(
        taxonomy_resolver=_resolver(),
        id_factory=lambda: application_id,
        renderer=renderer,
    )


def test_prepare_returns_packet_only_after_validation_and_render(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()
    result = _service().prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )

    assert result.status == "PREPARED"
    assert result.packet is not None
    assert Path(result.packet.cv_pdf_path).exists()
    assert result.packet.application_track_id == "tech"
    assert result.packet.selected_intent == "CAREER"
    assert len(result.packet.cv_sha256) == 64
    assert len(result.packet.packet_sha256) == 64


def test_missing_minimum_evidence_writes_no_pdf(tmp_path: Path) -> None:
    master, catalog, policy = _inputs(minimum=False)
    result = _service().prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )

    assert result.status == "BLOCKED_MISSING_FACTS"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []


def test_track_unavailable_writes_no_pdf(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()
    result = _service().prepare(
        assessment=_assessment(with_track=False),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )

    assert result.status == "BLOCKED_TRACK_UNAVAILABLE"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []


def test_validation_failure_does_not_call_renderer(monkeypatch, tmp_path: Path) -> None:
    master, catalog, policy = _inputs()

    def invalid_validation(**kwargs):
        return ValidationResult(
            valid=False,
            errors=[
                ValidationIssue(
                    code="claim_validation_failed",
                    message="blocked",
                )
            ],
        )

    class RendererMustNotRun:
        renderer_version = "never"

        def render(self, *args, **kwargs):
            raise AssertionError("renderer must not run after validation failure")

    monkeypatch.setattr("app.cv.service.validate_cv", invalid_validation)
    result = _service(renderer=RendererMustNotRun()).prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )

    assert result.status == "BLOCKED_VALIDATION"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []


def test_render_failure_is_blocked_and_partial_pdf_removed(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()

    class BrokenRenderer(ATSRenderer):
        def render(self, document, validation, output_path):
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"partial")
            raise OSError("fictional renderer failure")

    result = _service(renderer=BrokenRenderer()).prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path,
        now=NOW,
    )

    assert result.status == "BLOCKED_RENDER"
    assert result.packet is None
    assert list(tmp_path.rglob("*.pdf")) == []


def test_packet_hash_excludes_id_time_and_path(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()
    first = _service("app-a").prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path / "a",
        now=NOW,
    )
    second = _service("app-b").prepare(
        assessment=_assessment(),
        master_facts=master,
        evidence_catalog=catalog,
        policy=policy,
        output_root=tmp_path / "b",
        now=NOW + timedelta(hours=1),
    )

    assert first.packet is not None
    assert second.packet is not None
    assert first.packet.packet_sha256 == second.packet.packet_sha256


def test_semantic_fact_change_changes_packet_hash(tmp_path: Path) -> None:
    first_master, first_catalog, policy = _inputs(project_value="Geo platform project")
    second_master, second_catalog, _ = _inputs(project_value="Different verified project")

    first = _service("app-a").prepare(
        assessment=_assessment(),
        master_facts=first_master,
        evidence_catalog=first_catalog,
        policy=policy,
        output_root=tmp_path / "a",
        now=NOW,
    )
    second = _service("app-b").prepare(
        assessment=_assessment(),
        master_facts=second_master,
        evidence_catalog=second_catalog,
        policy=policy,
        output_root=tmp_path / "b",
        now=NOW,
    )

    assert first.packet is not None
    assert second.packet is not None
    assert first.packet.packet_sha256 != second.packet.packet_sha256


def test_prepare_rejects_naive_now_before_any_output(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()
    with pytest.raises(ValueError, match="timezone-aware"):
        _service().prepare(
            assessment=_assessment(),
            master_facts=master,
            evidence_catalog=catalog,
            policy=policy,
            output_root=tmp_path,
            now=datetime(2026, 8, 28, 12, 0),
        )
    assert list(tmp_path.rglob("*.pdf")) == []


def test_service_validates_catalog_references_before_preparation(tmp_path: Path) -> None:
    master, catalog, policy = _inputs()
    broken_module = catalog.modules[0].model_copy(
        update={"fact_ids": [*catalog.modules[0].fact_ids, "ghost-fact"]}
    )
    broken_catalog = catalog.model_copy(update={"modules": [broken_module]})

    with pytest.raises(ValueError, match="missing fact"):
        _service().prepare(
            assessment=_assessment(),
            master_facts=master,
            evidence_catalog=broken_catalog,
            policy=policy,
            output_root=tmp_path,
            now=NOW,
        )

    assert list(tmp_path.rglob("*.pdf")) == []
