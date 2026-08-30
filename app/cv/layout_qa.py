from __future__ import annotations

from pypdf import PdfReader

from app.cv.models import (
    LayoutQAResult,
    RenderedCVArtifact,
    RenderLayoutMetrics,
    ValidationIssue,
)

LOW_UTILIZATION = 0.58
HIGH_UTILIZATION = 0.96
TINY_TRAILING_PAGE_MAX_TOTAL_UTILIZATION = 1.20
MAX_PAGES = 2
MIN_BODY_FONT = 9.0
MAX_HEADLINE_LINES = 2


class LayoutQA:
    def evaluate(
        self,
        artifact: RenderedCVArtifact,
        metrics: RenderLayoutMetrics,
        *,
        expected_nonempty: bool = True,
    ) -> LayoutQAResult:
        reader = PdfReader(artifact.path)
        page_count = len(reader.pages)
        extracted_text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        ).strip()
        used_height_ratio = metrics.rendered_content_height / metrics.usable_height

        warnings: list[ValidationIssue] = []
        errors: list[ValidationIssue] = []

        if page_count == 0:
            errors.append(
                ValidationIssue(
                    code="layout_zero_pages",
                    message="rendered CV contains no pages",
                )
            )
        elif page_count > MAX_PAGES:
            errors.append(
                ValidationIssue(
                    code="layout_page_count_exceeded",
                    message=f"rendered CV exceeds the {MAX_PAGES}-page limit",
                )
            )

        if metrics.body_font_size < MIN_BODY_FONT:
            errors.append(
                ValidationIssue(
                    code="layout_body_font_too_small",
                    message=f"body font must be at least {MIN_BODY_FONT:g} pt",
                )
            )

        if expected_nonempty and not extracted_text:
            errors.append(
                ValidationIssue(
                    code="layout_missing_extractable_text",
                    message="rendered CV has no selectable text",
                )
            )

        if used_height_ratio < LOW_UTILIZATION:
            warnings.append(
                ValidationIssue(
                    code="layout_low_utilization",
                    message="rendered CV uses unusually little of the available page height",
                )
            )
        elif used_height_ratio > HIGH_UTILIZATION:
            warnings.append(
                ValidationIssue(
                    code="layout_high_utilization",
                    message="rendered CV uses unusually much of the available page height",
                )
            )

        if (
            page_count == 2
            and metrics.page_count == 2
            and 1.0 < used_height_ratio < TINY_TRAILING_PAGE_MAX_TOTAL_UTILIZATION
        ):
            warnings.append(
                ValidationIssue(
                    code="layout_tiny_trailing_page",
                    message="second CV page contains only a small trailing content block",
                )
            )

        if metrics.headline_line_count > MAX_HEADLINE_LINES:
            warnings.append(
                ValidationIssue(
                    code="layout_headline_wrap",
                    message=f"target headline wraps beyond {MAX_HEADLINE_LINES} lines",
                )
            )

        return LayoutQAResult(
            valid=not errors,
            page_count=page_count,
            warnings=warnings,
            errors=errors,
            used_height_ratio=used_height_ratio,
        )
