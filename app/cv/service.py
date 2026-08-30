from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.cv.composer import COMPOSER_VERSION, compose_cv
from app.cv.hashing import canonical_sha256
from app.cv.layout_qa import LayoutQA
from app.cv.loaders import validate_catalog_against_facts
from app.cv.models import (
    ApplicationPacket,
    CVPolicy,
    EvidenceCatalogSnapshot,
    MasterFactsSnapshot,
    PreparationResult,
    ValidationIssue,
)
from app.cv.renderer import ATSRenderer
from app.cv.selector import select_evidence
from app.cv.track import (
    CVPreparationError,
    require_minimum_evidence,
    resolve_application_track,
)
from app.cv.validator import validate_cv
from app.radar.models import RadarAssessment
from app.radar.taxonomy import TaxonomyResolver


class CVPreparationService:
    def __init__(
        self,
        taxonomy_resolver: TaxonomyResolver,
        id_factory: Callable[[], str] | None = None,
        renderer: ATSRenderer | None = None,
        layout_qa: LayoutQA | None = None,
    ) -> None:
        self.taxonomy_resolver = taxonomy_resolver
        self.id_factory = id_factory or (lambda: str(uuid4()))
        self.renderer = renderer or ATSRenderer()
        self.layout_qa = layout_qa or LayoutQA()

    def prepare(
        self,
        assessment: RadarAssessment,
        master_facts: MasterFactsSnapshot,
        evidence_catalog: EvidenceCatalogSnapshot,
        policy: CVPolicy,
        output_root: str | Path,
        now: datetime,
    ) -> PreparationResult:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

        validate_catalog_against_facts(evidence_catalog, master_facts)

        try:
            application_track_id = resolve_application_track(assessment)
        except CVPreparationError as exc:
            if exc.code != "track_unavailable":
                raise
            return _blocked(
                "BLOCKED_TRACK_UNAVAILABLE",
                code=exc.code,
                message="No winning application track is available",
            )

        if assessment.selected_intent is None:
            return _blocked(
                "BLOCKED_TRACK_UNAVAILABLE",
                code="selected_intent_unavailable",
                message="Selected radar intent is unavailable",
            )

        try:
            require_minimum_evidence(
                application_track_id,
                master_facts,
                evidence_catalog,
                policy,
            )
        except CVPreparationError as exc:
            if exc.code != "insufficient_verified_evidence":
                raise
            return _blocked(
                "BLOCKED_MISSING_FACTS",
                code=exc.code,
                message="Selected track lacks minimum verified CV evidence",
            )

        selection = select_evidence(
            enrichment=assessment.enrichment,
            application_track_id=application_track_id,
            master_facts=master_facts,
            evidence_catalog=evidence_catalog,
            policy=policy,
            resolver=self.taxonomy_resolver,
        )
        document = compose_cv(
            selection=selection,
            master_facts=master_facts,
            evidence_catalog=evidence_catalog,
            policy=policy,
        )
        validation = validate_cv(
            document=document,
            master_facts=master_facts,
            evidence_catalog=evidence_catalog,
            application_track_id=application_track_id,
            selection=selection,
        )
        if not validation.valid:
            return PreparationResult(
                status="BLOCKED_VALIDATION",
                errors=validation.errors,
                warnings=validation.warnings,
            )

        application_id = self.id_factory()
        output_path = Path(output_root) / application_id / "cv.pdf"
        try:
            artifact = self.renderer.render(document, validation, output_path)
        except (OSError, ValueError):
            _remove_partial_pdf(output_path)
            return _blocked(
                "BLOCKED_RENDER",
                code="render_failed",
                message="CV PDF rendering failed",
                warnings=validation.warnings,
            )

        metrics = getattr(self.renderer, "layout_metrics", None)
        if metrics is None:
            _remove_partial_pdf(output_path)
            return _blocked(
                "BLOCKED_RENDER",
                code="layout_metrics_missing",
                message="CV renderer did not produce layout metrics",
                warnings=validation.warnings,
            )

        try:
            layout_result = self.layout_qa.evaluate(
                artifact,
                metrics,
                expected_nonempty=bool(document.claims),
            )
        except (OSError, ValueError):
            _remove_partial_pdf(output_path)
            return _blocked(
                "BLOCKED_RENDER",
                code="layout_qa_failed",
                message="CV layout quality check failed",
                warnings=validation.warnings,
            )

        combined_warnings = [*validation.warnings, *layout_result.warnings]
        if not layout_result.valid:
            _remove_partial_pdf(output_path)
            errors = layout_result.errors or [
                ValidationIssue(
                    code="layout_qa_failed",
                    message="CV layout quality check failed",
                )
            ]
            return PreparationResult(
                status="BLOCKED_RENDER",
                errors=errors,
                warnings=combined_warnings,
            )

        opportunity_snapshot_hash = canonical_sha256(
            assessment.opportunity.model_dump(mode="json")
        )
        packet = ApplicationPacket(
            application_id=application_id,
            opportunity_id=assessment.opportunity.id,
            opportunity_snapshot_hash=opportunity_snapshot_hash,
            radar_batch_id=None,
            selected_intent=assessment.selected_intent,
            application_track_id=application_track_id,
            career_match=assessment.career_match,
            income_viability=assessment.income_viability,
            confidence_score=assessment.confidence_score,
            scoring_version=assessment.scoring_version,
            extractor_version=assessment.extractor_version,
            alias_registry_version=assessment.alias_registry_version,
            taxonomy_versions=assessment.taxonomy_versions,
            master_facts_version=master_facts.content_sha256,
            evidence_catalog_version=evidence_catalog.content_sha256,
            composer_version=COMPOSER_VERSION,
            cv_document_version=document.document_version,
            renderer_version=artifact.renderer_version,
            selected_fact_ids=selection.selected_fact_ids,
            selected_evidence_ids=selection.selected_evidence_ids,
            unresolved_gaps=selection.unsupported_requirements,
            cv_document=document,
            cv_pdf_path=artifact.path,
            cv_sha256=artifact.sha256,
            packet_sha256="0" * 64,
            created_at=now,
        )
        packet_hash = canonical_sha256(_packet_content_payload(packet))
        final_packet = packet.model_copy(update={"packet_sha256": packet_hash})
        return PreparationResult(
            status="PREPARED",
            packet=final_packet,
            warnings=combined_warnings,
        )


def _packet_content_payload(packet: ApplicationPacket) -> dict:
    return {
        "opportunity_id": packet.opportunity_id,
        "opportunity_snapshot_hash": packet.opportunity_snapshot_hash,
        "radar_batch_id": packet.radar_batch_id,
        "selected_intent": packet.selected_intent,
        "application_track_id": packet.application_track_id,
        "career_match": packet.career_match,
        "income_viability": packet.income_viability,
        "confidence_score": packet.confidence_score,
        "scoring_version": packet.scoring_version,
        "extractor_version": packet.extractor_version,
        "alias_registry_version": packet.alias_registry_version,
        "taxonomy_versions": packet.taxonomy_versions,
        "master_facts_version": packet.master_facts_version,
        "evidence_catalog_version": packet.evidence_catalog_version,
        "composer_version": packet.composer_version,
        "cv_document_version": packet.cv_document_version,
        "renderer_version": packet.renderer_version,
        "selected_fact_ids": packet.selected_fact_ids,
        "selected_evidence_ids": packet.selected_evidence_ids,
        "unresolved_gaps": packet.unresolved_gaps,
        "cv_document": packet.cv_document.model_dump(mode="json"),
        "cv_sha256": packet.cv_sha256,
        "status": packet.status,
    }


def _blocked(
    status: str,
    *,
    code: str,
    message: str,
    warnings: list[ValidationIssue] | None = None,
) -> PreparationResult:
    return PreparationResult(
        status=status,
        errors=[ValidationIssue(code=code, message=message)],
        warnings=warnings or [],
    )


def _remove_partial_pdf(output_path: Path) -> None:
    try:
        output_path.unlink(missing_ok=True)
    finally:
        parent = output_path.parent
        try:
            parent.rmdir()
        except OSError:
            pass
