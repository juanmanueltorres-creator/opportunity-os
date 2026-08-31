from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.cv.composer import COMPOSER_VERSION, compose_cv
from app.cv.filename import build_cv_filename
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
from app.cv.recruiter_composer import compose_recruiter_document, reduce_recruiter_document
from app.cv.recruiter_models import RecruiterDocumentModel
from app.cv.recruiter_policy import RecruiterPolicy, load_recruiter_policy
from app.cv.recruiter_qa import RecruiterQualityQA
from app.cv.recruiter_validator import validate_recruiter_document
from app.cv.renderer import ATSRenderer
from app.cv.renderers.rendercv_typst import RenderCVTypstRenderer
from app.cv.selector import select_evidence
from app.cv.track import (
    CVPreparationError,
    require_minimum_evidence,
    resolve_application_track,
)
from app.cv.validator import validate_cv
from app.radar.models import LanguageDecision, RadarAssessment
from app.radar.taxonomy import TaxonomyResolver

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_RECRUITER_POLICY_PATH = _PROJECT_ROOT / "config" / "recruiter_policy.yaml"
_REDUCIBLE_QA_CODES = {
    "recruiter_one_page_failed",
    "recruiter_overflow_detected",
}


class CVPreparationService:
    def __init__(
        self,
        taxonomy_resolver: TaxonomyResolver,
        id_factory: Callable[[], str] | None = None,
        renderer: ATSRenderer | None = None,
        layout_qa: LayoutQA | None = None,
        recruiter_policy: RecruiterPolicy | None = None,
        recruiter_renderer: RenderCVTypstRenderer | None = None,
        recruiter_qa: RecruiterQualityQA | None = None,
    ) -> None:
        self.taxonomy_resolver = taxonomy_resolver
        self.id_factory = id_factory or (lambda: str(uuid4()))
        self.renderer = renderer
        self.layout_qa = layout_qa
        self.recruiter_policy = recruiter_policy or load_recruiter_policy(
            _DEFAULT_RECRUITER_POLICY_PATH
        )
        self.recruiter_renderer = recruiter_renderer or RenderCVTypstRenderer()
        self.recruiter_qa = recruiter_qa or RecruiterQualityQA()

    def prepare(
        self,
        assessment: RadarAssessment,
        master_facts: MasterFactsSnapshot,
        evidence_catalog: EvidenceCatalogSnapshot,
        policy: CVPolicy,
        output_root: str | Path,
        now: datetime,
        language_decision: LanguageDecision,
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
            language=language_decision.language,
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

        try:
            recruiter_document = compose_recruiter_document(
                document=document,
                validation=validation,
                selection=selection,
                policy=self.recruiter_policy,
            )
        except ValueError:
            return _blocked(
                "BLOCKED_VALIDATION",
                code="recruiter_composition_failed",
                message="Recruiter document composition failed",
                warnings=validation.warnings,
            )

        recruiter_validation = validate_recruiter_document(
            recruiter_document=recruiter_document,
            source_document=document,
            source_validation=validation,
            policy=self.recruiter_policy,
        )
        if not recruiter_validation.valid:
            return PreparationResult(
                status="BLOCKED_VALIDATION",
                errors=recruiter_validation.errors,
                warnings=[*validation.warnings, *recruiter_validation.warnings],
            )

        application_id = self.id_factory()
        candidate_name = next(
            claim.text for claim in document.claims if claim.kind == "identity"
        )
        output_path = (
            Path(output_root)
            / application_id
            / build_cv_filename(
                candidate_name,
                assessment.opportunity.title,
                assessment.opportunity.company,
            )
        )
        final_recruiter_document = recruiter_document
        final_recruiter_validation = recruiter_validation
        final_render_result = None
        final_qa_result = None
        max_reductions = _max_reduction_actions(recruiter_document)

        for reduction_index in range(max_reductions + 1):
            try:
                render_result = self.recruiter_renderer.render(
                    final_recruiter_document,
                    document,
                    output_path,
                    self.recruiter_policy,
                )
            except (OSError, ValueError):
                _remove_partial_pdf(output_path)
                return _blocked(
                    "BLOCKED_RENDER",
                    code="render_failed",
                    message="Recruiter CV PDF rendering failed",
                    warnings=[
                        *validation.warnings,
                        *final_recruiter_validation.warnings,
                    ],
                )

            try:
                qa_result = self.recruiter_qa.evaluate(
                    render_result,
                    final_recruiter_document,
                    document,
                    self.recruiter_policy,
                )
            except (OSError, ValueError):
                _remove_partial_pdf(output_path)
                return _blocked(
                    "BLOCKED_RENDER",
                    code="recruiter_qa_failed",
                    message="Recruiter CV quality validation failed",
                    warnings=[
                        *validation.warnings,
                        *final_recruiter_validation.warnings,
                    ],
                )

            if qa_result.valid:
                final_render_result = render_result
                final_qa_result = qa_result
                break

            combined_warnings = [
                *validation.warnings,
                *final_recruiter_validation.warnings,
                *qa_result.warnings,
            ]
            if not _qa_failure_is_reducible(qa_result.errors):
                _remove_partial_pdf(output_path)
                return PreparationResult(
                    status="BLOCKED_RENDER",
                    errors=qa_result.errors,
                    warnings=combined_warnings,
                )

            if reduction_index >= max_reductions:
                _remove_partial_pdf(output_path)
                return PreparationResult(
                    status="BLOCKED_RENDER",
                    errors=qa_result.errors,
                    warnings=combined_warnings,
                )

            reduced_document = reduce_recruiter_document(
                final_recruiter_document,
                self.recruiter_policy,
                step=0,
            )
            if (
                reduced_document.model_dump(mode="json")
                == final_recruiter_document.model_dump(mode="json")
                or not _preserves_required_sections(reduced_document, policy)
            ):
                _remove_partial_pdf(output_path)
                return PreparationResult(
                    status="BLOCKED_RENDER",
                    errors=qa_result.errors,
                    warnings=combined_warnings,
                )

            reduced_validation = validate_recruiter_document(
                recruiter_document=reduced_document,
                source_document=document,
                source_validation=validation,
                policy=self.recruiter_policy,
            )
            if not reduced_validation.valid:
                _remove_partial_pdf(output_path)
                return PreparationResult(
                    status="BLOCKED_VALIDATION",
                    errors=reduced_validation.errors,
                    warnings=[*validation.warnings, *reduced_validation.warnings],
                )

            final_recruiter_document = reduced_document
            final_recruiter_validation = reduced_validation

        if final_render_result is None or final_qa_result is None:
            _remove_partial_pdf(output_path)
            return _blocked(
                "BLOCKED_RENDER",
                code="recruiter_one_page_failed",
                message="Recruiter PDF could not satisfy the one-page quality contract",
                warnings=[
                    *validation.warnings,
                    *final_recruiter_validation.warnings,
                ],
            )

        artifact = final_render_result.artifact
        combined_warnings = [
            *validation.warnings,
            *final_recruiter_validation.warnings,
            *final_qa_result.warnings,
        ]
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
            recruiter_policy_version=self.recruiter_policy.version,
            renderer_version=artifact.renderer_version,
            selected_fact_ids=selection.selected_fact_ids,
            selected_evidence_ids=selection.selected_evidence_ids,
            unresolved_gaps=selection.unsupported_requirements,
            language_decision=language_decision,
            cv_document=document,
            recruiter_document=final_recruiter_document,
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
        "recruiter_policy_version": packet.recruiter_policy_version,
        "renderer_version": packet.renderer_version,
        "selected_fact_ids": packet.selected_fact_ids,
        "selected_evidence_ids": packet.selected_evidence_ids,
        "unresolved_gaps": packet.unresolved_gaps,
        "language_decision": packet.language_decision.model_dump(mode="json"),
        "cv_document": packet.cv_document.model_dump(mode="json"),
        "recruiter_document": packet.recruiter_document.model_dump(mode="json"),
        "cv_sha256": packet.cv_sha256,
        "status": packet.status,
    }


def _max_reduction_actions(document: RecruiterDocumentModel) -> int:
    return (
        max(0, len(document.link_claim_ids) - 1)
        + sum(len(group.skill_claim_ids) for group in document.technology_groups)
        + max(0, len(document.selected_project_claim_ids) - 2)
        + max(0, len(document.experience_entries) - 1)
        + max(0, len(document.education_claim_ids) - 1)
    )


def _qa_failure_is_reducible(errors: list[ValidationIssue]) -> bool:
    return bool(errors) and {error.code for error in errors}.issubset(_REDUCIBLE_QA_CODES)


def _preserves_required_sections(
    document: RecruiterDocumentModel,
    policy: CVPolicy,
) -> bool:
    counts = {
        "summary": len(document.profile_claim_ids),
        "skills": sum(
            len(group.skill_claim_ids) for group in document.technology_groups
        ),
        "experience": len(document.experience_entries),
        "projects": len(document.selected_project_claim_ids),
        "education": len(document.education_claim_ids),
        "languages": len(document.language_claim_ids),
        "links": len(document.link_claim_ids),
    }
    return all(counts.get(section, 1) > 0 for section in policy.required_sections)


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
