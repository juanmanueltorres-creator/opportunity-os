from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from app.cv.models import CVDocumentModel, ValidationIssue
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterQAResult,
    RecruiterRenderResult,
)
from app.cv.render_policy import RenderPolicy

_PAGE_SIZES_POINTS = {
    "A4": (595.276, 841.89),
    "LETTER": (612.0, 792.0),
}
_PAGE_TOLERANCE_POINTS = 3.0


class RecruiterQualityQA:
    def evaluate(
        self,
        render_result: RecruiterRenderResult,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        policy: RenderPolicy,
    ) -> RecruiterQAResult:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        path = Path(render_result.artifact.path)

        try:
            document = pymupdf.open(path)
        except Exception:
            return RecruiterQAResult(
                valid=False,
                page_count=0,
                extracted_text="",
                errors=[
                    _issue(
                        "recruiter_pdf_unreadable",
                        "Recruiter PDF could not be opened for quality validation.",
                    )
                ],
            )

        try:
            page_count = len(document)
            if policy.max_pages == 1 and page_count != 1:
                errors.append(
                    _issue(
                        "recruiter_one_page_failed",
                        "Recruiter PDF must contain exactly one page.",
                    )
                )
            elif page_count > policy.max_pages:
                errors.append(
                    _issue(
                        "recruiter_page_count_exceeded",
                        "Recruiter PDF exceeds the configured maximum page count.",
                    )
                )
            elif page_count > policy.preferred_pages:
                warnings.append(
                    _issue(
                        "recruiter_preferred_page_count_exceeded",
                        "Recruiter PDF exceeds the preferred page count.",
                    )
                )

            if page_count > 0:
                expected_width, expected_height = _PAGE_SIZES_POINTS[policy.page_size]
                for page in document:
                    width = float(page.rect.width)
                    height = float(page.rect.height)
                    if not _is_page_size(
                        width,
                        height,
                        expected_width=expected_width,
                        expected_height=expected_height,
                    ):
                        errors.append(
                            _issue(
                                "recruiter_page_size_invalid",
                                f"Recruiter PDF page size must be {policy.page_size}.",
                            )
                        )
                        break

            extracted_text = "\n".join(page.get_text("text") for page in document).strip()
            if not extracted_text:
                errors.append(
                    _issue(
                        "recruiter_text_not_extractable",
                        "Recruiter PDF must contain extractable text.",
                    )
                )

            if render_result.metrics.body_font_size < policy.min_body_font_pt:
                errors.append(
                    _issue(
                        "recruiter_body_font_too_small",
                        "Recruiter PDF body font is below the minimum allowed size.",
                    )
                )

            if render_result.metrics.overflow_detected:
                errors.append(
                    _issue(
                        "recruiter_overflow_detected",
                        "Recruiter PDF contains rendered content outside page bounds.",
                    )
                )

            if any(page.get_images(full=True) for page in document):
                errors.append(
                    _issue(
                        "recruiter_raster_image_detected",
                        "Recruiter PDF must remain text-first and contain no raster images.",
                    )
                )

            if extracted_text:
                order_issue = _validate_claim_order(
                    extracted_text=extracted_text,
                    recruiter_document=recruiter_document,
                    source_document=source_document,
                )
                if order_issue is not None:
                    errors.append(order_issue)

            return RecruiterQAResult(
                valid=not errors,
                page_count=page_count,
                extracted_text=extracted_text,
                errors=errors,
                warnings=warnings,
            )
        finally:
            document.close()


def _validate_claim_order(
    *,
    extracted_text: str,
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
) -> ValidationIssue | None:
    claim_by_id = {claim.claim_id: claim for claim in source_document.claims}
    haystack = _normalize_text(extracted_text)
    cursor = 0

    for claim_id in recruiter_document.all_claim_ids():
        claim = claim_by_id.get(claim_id)
        if claim is None:
            return _issue(
                "recruiter_claim_text_missing",
                "Recruiter PDF references a claim absent from the semantic document.",
                claim_id=claim_id,
            )

        needle = _normalize_text(claim.text)
        position = haystack.find(needle, cursor)
        if position < 0:
            anywhere = haystack.find(needle)
            if anywhere < 0:
                return _issue(
                    "recruiter_claim_text_missing",
                    "Expected recruiter claim text is not extractable from the PDF.",
                    claim_id=claim_id,
                )
            return _issue(
                "recruiter_claim_order_invalid",
                "Recruiter claim text appears outside the canonical section order.",
                claim_id=claim_id,
            )
        cursor = position + len(needle)

    return None


def _normalize_text(value: str) -> str:
    normalized = value.replace("\u00ad", "").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _is_page_size(
    width: float,
    height: float,
    *,
    expected_width: float,
    expected_height: float,
) -> bool:
    return (
        abs(width - expected_width) <= _PAGE_TOLERANCE_POINTS
        and abs(height - expected_height) <= _PAGE_TOLERANCE_POINTS
    )


def _issue(code: str, message: str, *, claim_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, claim_id=claim_id)
