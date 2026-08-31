from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pymupdf

from app.models.domain import Opportunity
from app.radar.models import (
    ConfidenceAssessment,
    DerivedValue,
    EligibilityResult,
    OpportunityEnrichment,
    RadarAssessment,
    Requirement,
)
from scripts.render_recruiter_previews import render_previews

_A4_WIDTH_POINTS = 595.276
_A4_HEIGHT_POINTS = 841.89
_A4_HEIGHT_ROUNDED_POINTS = 842
_PAGE_TOLERANCE_POINTS = 3.0
_EXPECTED_RENDERER_VERSION = "rendercv-typst-v1"
_EXPECTED_LANGUAGE = "es"
_EXPECTED_LANGUAGE_BASIS = "market_location"
_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def verify_recruiter_pdf(path: Path) -> None:
    document = pymupdf.open(path)
    try:
        page_count = document.page_count
        if page_count != 1:
            raise RuntimeError(f"offline recruiter smoke expected one page, got {page_count}: {path}")

        page = document[0]
        if abs(float(page.rect.width) - _A4_WIDTH_POINTS) > _PAGE_TOLERANCE_POINTS:
            raise RuntimeError(f"offline recruiter smoke is not A4 width: {path}")
        if abs(float(page.rect.height) - _A4_HEIGHT_POINTS) > _PAGE_TOLERANCE_POINTS:
            raise RuntimeError(f"offline recruiter smoke is not A4 height: {path}")
        if round(float(page.rect.height)) != _A4_HEIGHT_ROUNDED_POINTS:
            raise RuntimeError(f"offline recruiter smoke has unexpected rounded A4 height: {path}")

        extracted_text = page.get_text().strip()
        if not extracted_text:
            raise RuntimeError(f"offline recruiter smoke has no selectable text: {path}")

        uris = {str(link.get("uri")) for link in page.get_links() if link.get("uri")}
        if not any(uri.startswith("mailto:") for uri in uris):
            raise RuntimeError(f"offline recruiter smoke has no mailto: URI: {path}")
        if not any(uri.startswith("https://") for uri in uris):
            raise RuntimeError(f"offline recruiter smoke has no https:// URI: {path}")
    finally:
        document.close()


def _fictional_assessment() -> RadarAssessment:
    opportunity = Opportunity(
        id="opp-offline-smoke-1",
        source="manual",
        source_id="fixture-offline-smoke-1",
        source_url="https://example.test/jobs/offline-smoke-1",
        company="Example Spatial Labs",
        title="GIS Developer",
        description="Required: PostGIS.",
        discovered_at=_NOW,
        published_at=_NOW,
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
        taxonomy_versions={},
        created_at=_NOW,
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


def _write_prepare_inputs(root: Path) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    assessment_path = root / "radar_assessment.json"
    assessment_path.write_text(_fictional_assessment().model_dump_json(indent=2), encoding="utf-8")

    master_path = root / "master_facts.fixture.yaml"
    master_path.write_text(
        """schema_version: v1
facts:
  - id: identity-name
    kind: identity
    value: Alex Example
    display_values: {en: Alex Example, es: Alex Example}
    track_ids: [tech]
    verified: true
    verification_method: manual_confirmation
    verified_at: '2026-08-28T12:00:00+00:00'
  - id: contact-email
    kind: contact
    value: alex@example.test
    display_values: {en: alex@example.test, es: alex@example.test}
    track_ids: [tech]
    verified: true
    verification_method: manual_confirmation
    verified_at: '2026-08-28T12:00:00+00:00'
  - id: link-github
    kind: link
    value: https://github.com/example
    display_values: {en: https://github.com/example, es: https://github.com/example}
    track_ids: [tech]
    verified: true
    verification_method: manual_confirmation
    verified_at: '2026-08-28T12:00:00+00:00'
  - id: role-primary
    kind: role
    value: GIS Developer
    display_values: {en: GIS Developer, es: Desarrollador GIS}
    track_ids: [tech]
    verified: true
    verification_method: repository_evidence
    verified_at: '2026-08-28T12:00:00+00:00'
    source_ref: https://example.test/evidence/role
  - id: skill-postgis
    kind: skill
    value: PostGIS
    display_values: {en: PostGIS, es: PostGIS}
    track_ids: [tech]
    verified: true
    verification_method: repository_evidence
    verified_at: '2026-08-28T12:00:00+00:00'
    source_ref: https://example.test/evidence/postgis
  - id: project-geo
    kind: project
    value: Geo platform project
    display_values: {en: Geo platform project, es: Proyecto de plataforma geoespacial}
    track_ids: [tech]
    verified: true
    verification_method: repository_evidence
    verified_at: '2026-08-28T12:00:00+00:00'
    source_ref: https://example.test/evidence/project
""",
        encoding="utf-8",
    )

    catalog_path = root / "evidence_catalog.fixture.yaml"
    catalog_path.write_text(
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
    return assessment_path, master_path, catalog_path


def verify_canonical_prepare(*, source_root: Path, output_dir: Path) -> Path:
    fixture_root = output_dir / "canonical-prepare-fixture"
    application_root = output_dir / "canonical-applications"
    assessment_path, master_path, catalog_path = _write_prepare_inputs(fixture_root)

    command = [
        sys.executable,
        "-m",
        "app.application.prepare",
        "--opportunity",
        str(assessment_path),
        "--master-facts",
        str(master_path),
        "--evidence-catalog",
        str(catalog_path),
        "--recruiter-policy",
        str(source_root / "config" / "recruiter_policy.yaml"),
        "--output-root",
        str(application_root),
    ]
    completed = subprocess.run(
        command,
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "canonical app.application.prepare failed in offline runtime: "
            f"exit={completed.returncode} stderr={completed.stderr.strip()!r} "
            f"stdout={completed.stdout.strip()!r}"
        )

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "canonical prepare did not emit valid JSON: "
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        ) from exc

    if result.get("status") != "PREPARED":
        raise RuntimeError(f"canonical prepare did not reach PREPARED: {result!r}")
    if result.get("page_count") != 1:
        raise RuntimeError(f"canonical PREPARED output is not one page: {result!r}")
    if result.get("language") != _EXPECTED_LANGUAGE:
        raise RuntimeError(
            "offline application language mismatch: "
            f"expected {_EXPECTED_LANGUAGE!r}, got {result.get('language')!r}"
        )
    if result.get("language_basis") != _EXPECTED_LANGUAGE_BASIS:
        raise RuntimeError(
            "offline application language mismatch: "
            f"expected basis {_EXPECTED_LANGUAGE_BASIS!r}, got {result.get('language_basis')!r}"
        )

    pdf_path = Path(str(result.get("cv_pdf_path", "")))
    if not pdf_path.is_file():
        raise RuntimeError(f"canonical PREPARED PDF is missing: {pdf_path}")
    packet_path = pdf_path.with_name("application_packet.json")
    if not packet_path.is_file():
        raise RuntimeError(f"canonical PREPARED application_packet.json is missing: {packet_path}")

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if packet.get("status") != "PREPARED":
        raise RuntimeError("application packet is not PREPARED")
    if packet.get("renderer_version") != _EXPECTED_RENDERER_VERSION:
        raise RuntimeError(
            "application packet renderer mismatch: "
            f"expected {_EXPECTED_RENDERER_VERSION}, got {packet.get('renderer_version')!r}"
        )

    language_decision = packet.get("language_decision")
    cv_document = packet.get("cv_document")
    if not isinstance(language_decision, dict) or not isinstance(cv_document, dict):
        raise RuntimeError("offline application language mismatch: packet language metadata missing")
    packet_language = language_decision.get("language")
    packet_basis = language_decision.get("basis")
    cv_language = cv_document.get("language")
    if not (
        packet_language
        == cv_language
        == result.get("language")
        == _EXPECTED_LANGUAGE
    ):
        raise RuntimeError(
            "offline application language mismatch: "
            f"packet={packet_language!r} cv={cv_language!r} cli={result.get('language')!r}"
        )
    if packet_basis != result.get("language_basis") or packet_basis != _EXPECTED_LANGUAGE_BASIS:
        raise RuntimeError(
            "offline application language mismatch: "
            f"packet_basis={packet_basis!r} cli_basis={result.get('language_basis')!r}"
        )

    verify_recruiter_pdf(pdf_path)
    return pdf_path


def verify_runtime(output_dir: Path) -> list[Path]:
    source_root = Path(__file__).resolve().parents[1]
    output_dir = output_dir.resolve()
    previous_cwd = Path.cwd()
    os.chdir(source_root)
    try:
        previews = render_previews(output_dir / "recruiter-previews")
        canonical_pdf = verify_canonical_prepare(source_root=source_root, output_dir=output_dir)
    finally:
        os.chdir(previous_cwd)

    if len(previews) != 2:
        raise RuntimeError(f"offline recruiter smoke expected two fictional previews, got {len(previews)}")
    for output in previews:
        verify_recruiter_pdf(output)
    return [*previews, canonical_pdf]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify recruiter previews and the complete canonical application prepare path "
            "from a bundled offline runtime."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/ci/offline-runtime-smoke"),
    )
    args = parser.parse_args()

    for output in verify_runtime(args.output_dir):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
