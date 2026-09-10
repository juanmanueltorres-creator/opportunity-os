from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pymupdf

from app.cv.layout.models import LayoutProfile
from app.cv.models import CVDocumentModel, ValidationIssue
from app.cv.recruiter_models import RecruiterDocumentModel, RecruiterRenderResult
from app.cv.visual_models import VisualMetrics, VisualQAResult
from app.cv.visual_policy import VisualPolicy, density_thresholds_for_profile

_LIST_MARKER = re.compile(r"^(?:[-•▪*]|\d+[.)])\s+")


class VisualQualityQA:
    def evaluate(
        self,
        render_result: RecruiterRenderResult,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        layout_profile: LayoutProfile,
        policy: VisualPolicy,
    ) -> VisualQAResult:
        path = Path(render_result.artifact.path)
        document = pymupdf.open(path)
        try:
            page_count = len(document)
            page_line_counts: list[int] = []
            densities: list[float] = []
            all_font_sizes: set[float] = set()
            max_block_lines = 0
            max_block_chars = 0
            max_internal_gap_ratio = 0.0
            content_bottom_ratio: float | None = None
            warnings: list[ValidationIssue] = []
            errors: list[ValidationIssue] = []

            for page in document:
                lines = _text_lines(page)
                page_line_counts.append(len(lines))
                height_inches = float(page.rect.height) / 72.0
                densities.append(len(lines) / height_inches if height_inches > 0 else 0.0)
                all_font_sizes.update(_span_font_sizes(page))

                block_lines, block_chars, block_wall_warning, block_wall_error = _max_block_shape(
                    page, policy
                )
                max_block_lines = max(max_block_lines, block_lines)
                max_block_chars = max(max_block_chars, block_chars)
                if block_wall_error:
                    errors.append(
                        _issue(
                            "visual_wall_of_text_severe",
                            "Recruiter PDF contains an excessively dense prose block.",
                        )
                    )
                elif block_wall_warning:
                    warnings.append(
                        _issue(
                            "visual_wall_of_text",
                            "Recruiter PDF contains a visually dense prose block.",
                        )
                    )

                gap_ratio = _largest_internal_gap_ratio(page)
                max_internal_gap_ratio = max(max_internal_gap_ratio, gap_ratio)

                if _is_isolated_bottom_block(page, policy):
                    errors.append(
                        _issue(
                            "visual_isolated_bottom_block",
                            "Recruiter PDF contains an isolated text block near the page bottom.",
                        )
                    )

                orphan_state = _orphan_heading_state(
                    page,
                    policy=policy,
                    body_font_size=render_result.metrics.body_font_size,
                )
                if orphan_state == "error":
                    errors.append(
                        _issue(
                            "visual_orphan_heading",
                            "Recruiter PDF contains a heading stranded at the page bottom.",
                        )
                    )
                elif orphan_state == "warning":
                    warnings.append(
                        _issue(
                            "visual_orphan_heading_warning",
                            "Recruiter PDF contains a heading with very little following content.",
                        )
                    )

            if page_count == 1:
                content_bottom_ratio = _content_bottom_ratio(document[0])
                if len(recruiter_document.all_claim_ids()) >= policy.min_substantive_claims_for_underfill:
                    if content_bottom_ratio < policy.underfill_error_bottom_ratio:
                        errors.append(
                            _issue(
                                "visual_content_underfilled",
                                "Recruiter PDF leaves an excessive unused lower-page region.",
                            )
                        )
                    elif content_bottom_ratio < policy.underfill_warning_bottom_ratio:
                        warnings.append(
                            _issue(
                                "visual_content_underfilled_warning",
                                "Recruiter PDF leaves substantial unused lower-page space.",
                            )
                        )

            if max_internal_gap_ratio >= policy.large_gap_error_ratio:
                errors.append(
                    _issue(
                        "visual_internal_dead_zone",
                        "Recruiter PDF contains an excessive internal vertical dead zone.",
                    )
                )
            elif max_internal_gap_ratio >= policy.large_gap_warning_ratio:
                warnings.append(
                    _issue(
                        "visual_vertical_rhythm_uneven",
                        "Recruiter PDF has uneven vertical spacing between content regions.",
                    )
                )

            lines_per_page_inch = max(densities, default=0.0)
            density_warning, density_error = density_thresholds_for_profile(
                policy, layout_profile
            )
            if lines_per_page_inch > density_error:
                errors.append(
                    _issue(
                        "visual_overcompressed",
                        "Recruiter PDF has excessive rendered line density.",
                    )
                )
            elif lines_per_page_inch > density_warning:
                warnings.append(
                    _issue(
                        "visual_density_high",
                        "Recruiter PDF has high rendered line density.",
                    )
                )

            if render_result.metrics.headline_line_count > policy.max_headline_lines:
                errors.append(
                    _issue(
                        "visual_headline_too_tall",
                        "Recruiter PDF headline occupies too many rendered lines.",
                    )
                )

            if page_count > 0 and _hierarchy_is_flat(
                document,
                recruiter_document=recruiter_document,
                source_document=source_document,
                body_font_size=render_result.metrics.body_font_size,
                minimum_delta=policy.hierarchy_min_delta_pt,
            ):
                warnings.append(
                    _issue(
                        "visual_hierarchy_flat",
                        "Recruiter PDF has weak typographic separation between header and body.",
                    )
                )

            metrics = VisualMetrics(
                page_count=page_count,
                content_bottom_ratio=content_bottom_ratio,
                largest_internal_gap_ratio=(
                    max_internal_gap_ratio if page_count else None
                ),
                nonempty_line_count=sum(page_line_counts),
                lines_per_page_inch=lines_per_page_inch,
                max_text_block_lines=max_block_lines,
                max_text_block_chars=max_block_chars,
                headline_line_count=render_result.metrics.headline_line_count,
                body_font_size=render_result.metrics.body_font_size,
                observed_font_size_levels=sorted(all_font_sizes),
            )
            return VisualQAResult(
                valid=not errors,
                metrics=metrics,
                errors=_dedupe_issues(errors),
                warnings=_dedupe_issues(warnings),
            )
        finally:
            document.close()


def _text_blocks(page: pymupdf.Page) -> list[dict[str, Any]]:
    raw = page.get_text("dict")
    return [
        block
        for block in raw.get("blocks", [])
        if block.get("type") == 0 and _block_text(block).strip()
    ]


def _text_lines(page: pymupdf.Page) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for block in _text_blocks(page):
        for line in block.get("lines", []):
            text = _line_text(line).strip()
            if text:
                lines.append({**line, "text": text})
    return lines


def _line_text(line: dict[str, Any]) -> str:
    return "".join(str(span.get("text", "")) for span in line.get("spans", []))


def _block_text(block: dict[str, Any]) -> str:
    return "\n".join(
        _line_text(line) for line in block.get("lines", []) if _line_text(line).strip()
    )


def _span_font_sizes(page: pymupdf.Page) -> set[float]:
    sizes: set[float] = set()
    for line in _text_lines(page):
        for span in line.get("spans", []):
            size = float(span.get("size", 0.0))
            if size > 0:
                sizes.add(round(size, 2))
    return sizes


def _content_bottom_ratio(page: pymupdf.Page) -> float:
    blocks = _text_blocks(page)
    if not blocks or float(page.rect.height) <= 0:
        return 0.0
    bottom = max(float(block["bbox"][3]) for block in blocks)
    return max(0.0, min(1.0, bottom / float(page.rect.height)))


def _largest_internal_gap_ratio(page: pymupdf.Page) -> float:
    blocks = sorted(_text_blocks(page), key=lambda block: float(block["bbox"][1]))
    if len(blocks) < 2 or float(page.rect.height) <= 0:
        return 0.0
    largest = 0.0
    previous_bottom = float(blocks[0]["bbox"][3])
    for block in blocks[1:]:
        top = float(block["bbox"][1])
        largest = max(largest, max(0.0, top - previous_bottom))
        previous_bottom = max(previous_bottom, float(block["bbox"][3]))
    return largest / float(page.rect.height)


def _list_marker_ratio(lines: list[str]) -> float:
    if not lines:
        return 0.0
    marked = sum(1 for line in lines if _LIST_MARKER.match(line.strip()))
    return marked / len(lines)


def _max_block_shape(
    page: pymupdf.Page,
    policy: VisualPolicy,
) -> tuple[int, int, bool, bool]:
    maximum_lines = 0
    maximum_chars = 0
    warning = False
    error = False
    for block in _text_blocks(page):
        lines = [
            _line_text(line).strip()
            for line in block.get("lines", [])
            if _line_text(line).strip()
        ]
        line_count = len(lines)
        char_count = sum(len(line) for line in lines)
        maximum_lines = max(maximum_lines, line_count)
        maximum_chars = max(maximum_chars, char_count)
        if _list_marker_ratio(lines) > policy.wall_text_max_list_marker_ratio:
            continue
        if (
            line_count >= policy.wall_text_error_lines
            and char_count >= policy.wall_text_error_chars
        ):
            error = True
        elif (
            line_count >= policy.wall_text_warning_lines
            and char_count >= policy.wall_text_warning_chars
        ):
            warning = True
    return maximum_lines, maximum_chars, warning, error


def _is_isolated_bottom_block(page: pymupdf.Page, policy: VisualPolicy) -> bool:
    blocks = sorted(_text_blocks(page), key=lambda block: float(block["bbox"][1]))
    if len(blocks) < 2:
        return False
    page_height = float(page.rect.height)
    threshold = page_height * policy.isolated_bottom_start_ratio
    for index, block in enumerate(blocks[1:], start=1):
        top = float(block["bbox"][1])
        if top < threshold:
            continue
        previous_bottom = max(float(item["bbox"][3]) for item in blocks[:index])
        if top - previous_bottom >= policy.isolated_bottom_min_gap_pt:
            return True
    return False


def _orphan_heading_state(
    page: pymupdf.Page,
    *,
    policy: VisualPolicy,
    body_font_size: float,
) -> str | None:
    lines = sorted(_text_lines(page), key=lambda line: float(line["bbox"][1]))
    page_height = float(page.rect.height)
    for index, line in enumerate(lines):
        top = float(line["bbox"][1])
        if top < page_height * policy.orphan_heading_bottom_ratio:
            continue
        text = str(line["text"]).strip()
        if len(text) > 80:
            continue
        spans = line.get("spans", [])
        max_size = max((float(span.get("size", 0.0)) for span in spans), default=0.0)
        bold = any(
            "bold" in str(span.get("font", "")).casefold()
            or bool(int(span.get("flags", 0)) & 16)
            for span in spans
        )
        if not bold and max_size < body_font_size + policy.hierarchy_min_delta_pt:
            continue
        following = [
            candidate
            for candidate in lines[index + 1 :]
            if float(candidate["bbox"][1]) >= float(line["bbox"][3])
        ]
        if not following:
            return "error"
        if len(following) <= policy.orphan_heading_max_following_lines:
            return "warning"
    return None


def _hierarchy_is_flat(
    document: pymupdf.Document,
    *,
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
    body_font_size: float,
    minimum_delta: float,
) -> bool:
    claim_by_id = {claim.claim_id: claim.text for claim in source_document.claims}
    anchors = [
        claim_by_id.get(recruiter_document.identity_claim_id, ""),
        claim_by_id.get(recruiter_document.headline_claim_id, ""),
    ]
    anchor_sizes: list[float] = []
    normalized_anchors = {_normalize(anchor) for anchor in anchors if anchor}
    for page in document:
        for line in _text_lines(page):
            line_text = _normalize(str(line["text"]))
            if not any(anchor in line_text for anchor in normalized_anchors):
                continue
            anchor_sizes.extend(
                float(span.get("size", 0.0))
                for span in line.get("spans", [])
                if float(span.get("size", 0.0)) > 0
            )
    if not anchor_sizes:
        return False
    return max(anchor_sizes) - body_font_size < minimum_delta


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _issue(code: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, message=message)


def _dedupe_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    seen: set[str] = set()
    result: list[ValidationIssue] = []
    for issue in issues:
        if issue.code in seen:
            continue
        seen.add(issue.code)
        result.append(issue)
    return result
