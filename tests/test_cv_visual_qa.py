from __future__ import annotations

from pathlib import Path

import pymupdf

from app.cv.layout.models import LayoutProfile
from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance, RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.visual_policy import load_visual_policy
from app.cv.visual_qa import VisualQualityQA


PAGE_W = 595.28
PAGE_H = 841.89
BODY = 9.4


def _source_document(extra_claims: int = 8) -> CVDocumentModel:
    claims = [
        CVClaim(claim_id="fact:name", section="headline", kind="identity", text="Alex Example"),
        CVClaim(claim_id="fact:role", section="headline", kind="headline", text="Software Developer"),
    ]
    for index in range(extra_claims):
        claims.append(
            CVClaim(
                claim_id=f"fact:item{index}",
                section="summary",
                kind="summary",
                text=f"Evidence backed claim {index}",
            )
        )
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            claim.claim_id: ClaimProvenance(fact_ids=[claim.claim_id]) for claim in claims
        },
    )


def _recruiter_document(source: CVDocumentModel, claim_count: int | None = None) -> RecruiterDocumentModel:
    item_ids = [claim.claim_id for claim in source.claims if claim.claim_id.startswith("fact:item")]
    if claim_count is not None:
        # identity + headline are always visible; cap additional visible claims here.
        item_ids = item_ids[: max(0, claim_count - 2)]
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=[],
        profile_claim_ids=item_ids[:3],
        technology_groups=[],
        selected_project_claim_ids=[],
        project_entries=[],
        experience_entries=[],
        education_claim_ids=item_ids[3:7],
        language_claim_ids=item_ids[7:],
        link_claim_ids=[],
    )


def _profile(density: str = "balanced") -> LayoutProfile:
    ids = {
        "comfortable": "technical_clean",
        "balanced": "operations_clean",
        "compact": "compact_ats",
    }
    return LayoutProfile(
        version="layout-profile-v1",
        id=ids[density],
        design_path=f"config/layouts/{ids[density]}.yaml",
        density=density,
        emphasis="neutral",
        ats_mode="strict",
    )


def _render_result(path: Path, *, headline_lines: int = 1) -> RecruiterRenderResult:
    return RecruiterRenderResult(
        artifact=RenderedCVArtifact(
            path=str(path),
            sha256="c" * 64,
            renderer_version="visual-fixture",
        ),
        metrics=RecruiterRenderMetrics(
            body_font_size=BODY,
            headline_line_count=headline_lines,
            overflow_detected=False,
        ),
    )


def _evaluate(
    path: Path,
    *,
    claim_count: int = 10,
    density: str = "balanced",
    headline_lines: int = 1,
):
    source = _source_document(extra_claims=max(8, claim_count))
    recruiter = _recruiter_document(source, claim_count=claim_count)
    return VisualQualityQA().evaluate(
        render_result=_render_result(path, headline_lines=headline_lines),
        recruiter_document=recruiter,
        source_document=source,
        layout_profile=_profile(density),
        policy=load_visual_policy("config/visual_policy.yaml"),
    )


def _save(page_builder, path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=PAGE_W, height=PAGE_H)
    page_builder(page)
    document.save(path)
    document.close()
    return path


def _healthy(page):
    page.insert_text((48, 54), "Alex Example", fontsize=16)
    page.insert_text((48, 76), "Software Developer", fontsize=12)
    y = 115
    for index in range(8):
        page.insert_text((48, y), f"Evidence backed claim {index}", fontsize=BODY)
        y += 54


def test_healthy_balanced_page_is_visually_valid(tmp_path):
    pdf = _save(_healthy, tmp_path / "healthy.pdf")
    result = _evaluate(pdf)

    assert result.valid is True
    assert result.errors == []
    assert result.metrics.page_count == 1
    assert result.metrics.content_bottom_ratio is not None


def test_substantive_underfill_is_hard_failure(tmp_path):
    def build(page):
        page.insert_text((48, 48), "Alex Example", fontsize=16)
        page.insert_text((48, 68), "Software Developer", fontsize=12)
        for index in range(8):
            page.insert_text((48, 88 + index * 15), f"Evidence backed claim {index}", fontsize=BODY)

    result = _evaluate(_save(build, tmp_path / "underfill.pdf"))

    assert result.valid is False
    assert "visual_content_underfilled" in {issue.code for issue in result.errors}


def test_sparse_low_evidence_page_does_not_hard_fail_underfill(tmp_path):
    def build(page):
        page.insert_text((48, 48), "Alex Example", fontsize=16)
        page.insert_text((48, 70), "Software Developer", fontsize=12)
        page.insert_text((48, 100), "Evidence backed claim 0", fontsize=BODY)

    result = _evaluate(_save(build, tmp_path / "sparse.pdf"), claim_count=3)

    assert "visual_content_underfilled" not in {issue.code for issue in result.errors}


def test_isolated_bottom_block_is_hard_failure(tmp_path):
    def build(page):
        page.insert_text((48, 54), "Alex Example", fontsize=16)
        page.insert_text((48, 76), "Software Developer", fontsize=12)
        for index in range(8):
            page.insert_text((48, 110 + index * 25), f"Evidence backed claim {index}", fontsize=BODY)
        page.insert_text((48, 790), "Isolated note", fontsize=BODY)

    result = _evaluate(_save(build, tmp_path / "isolated.pdf"))

    assert "visual_isolated_bottom_block" in {issue.code for issue in result.errors}


def test_overcompressed_page_is_hard_failure_and_compact_profile_is_more_tolerant(tmp_path):
    def build(page):
        page.insert_text((48, 35), "Alex Example", fontsize=16)
        page.insert_text((48, 52), "Software Developer", fontsize=12)
        for index in range(78):
            page.insert_text((48, 65 + index * 9.3), f"dense line {index}", fontsize=7.5)

    pdf = _save(build, tmp_path / "dense.pdf")
    balanced = _evaluate(pdf, density="balanced")
    compact = _evaluate(pdf, density="compact")

    assert "visual_overcompressed" in {issue.code for issue in balanced.errors}
    assert compact.metrics.lines_per_page_inch == balanced.metrics.lines_per_page_inch


def test_moderate_prose_wall_warns_and_severe_prose_wall_fails(tmp_path):
    def moderate(page):
        page.insert_text((48, 45), "Alex Example", fontsize=16)
        page.insert_text((48, 67), "Software Developer", fontsize=12)
        text = "\n".join(
            f"Long paragraph line {i} with enough explanatory words to remain prose."
            for i in range(7)
        )
        page.insert_textbox(pymupdf.Rect(48, 110, 540, 310), text, fontsize=BODY)
        page.insert_text((48, 500), "Evidence backed claim 0", fontsize=BODY)

    def severe(page):
        page.insert_text((48, 45), "Alex Example", fontsize=16)
        page.insert_text((48, 67), "Software Developer", fontsize=12)
        text = "\n".join(
            f"Very long paragraph line {i} with enough explanatory words to create a severe prose wall."
            for i in range(12)
        )
        page.insert_textbox(pymupdf.Rect(48, 100, 540, 360), text, fontsize=BODY)
        page.insert_text((48, 500), "Evidence backed claim 0", fontsize=BODY)

    warning_result = _evaluate(_save(moderate, tmp_path / "wall-warning.pdf"), claim_count=3)
    error_result = _evaluate(_save(severe, tmp_path / "wall-error.pdf"), claim_count=3)

    assert "visual_wall_of_text" in {issue.code for issue in warning_result.warnings}
    assert "visual_wall_of_text_severe" in {issue.code for issue in error_result.errors}


def test_long_bullet_list_is_not_classified_as_prose_wall(tmp_path):
    def build(page):
        page.insert_text((48, 45), "Alex Example", fontsize=16)
        page.insert_text((48, 67), "Software Developer", fontsize=12)
        text = "\n".join(
            f"- Evidence item {i} with enough words to make this line deliberately long."
            for i in range(12)
        )
        page.insert_textbox(pymupdf.Rect(48, 100, 540, 360), text, fontsize=BODY)
        page.insert_text((48, 500), "Evidence backed claim 0", fontsize=BODY)

    result = _evaluate(_save(build, tmp_path / "bullets.pdf"), claim_count=3)
    codes = {issue.code for issue in [*result.errors, *result.warnings]}

    assert "visual_wall_of_text" not in codes
    assert "visual_wall_of_text_severe" not in codes


def test_large_internal_dead_zone_is_hard_failure(tmp_path):
    def build(page):
        page.insert_text((48, 45), "Alex Example", fontsize=16)
        page.insert_text((48, 67), "Software Developer", fontsize=12)
        page.insert_text((48, 110), "Evidence backed claim 0", fontsize=BODY)
        page.insert_text((48, 430), "Evidence backed claim 1", fontsize=BODY)
        page.insert_text((48, 470), "Evidence backed claim 2", fontsize=BODY)

    result = _evaluate(_save(build, tmp_path / "dead-zone.pdf"), claim_count=5)

    assert "visual_internal_dead_zone" in {issue.code for issue in result.errors}


def test_flat_hierarchy_is_warning_only(tmp_path):
    def build(page):
        page.insert_text((48, 45), "Alex Example", fontsize=BODY)
        page.insert_text((48, 67), "Software Developer", fontsize=BODY)
        y = 110
        for index in range(8):
            page.insert_text((48, y), f"Evidence backed claim {index}", fontsize=BODY)
            y += 55

    result = _evaluate(_save(build, tmp_path / "flat.pdf"))

    assert "visual_hierarchy_flat" in {issue.code for issue in result.warnings}


def test_headline_over_policy_line_limit_is_hard_failure(tmp_path):
    result = _evaluate(
        _save(_healthy, tmp_path / "headline.pdf"),
        headline_lines=3,
    )

    assert "visual_headline_too_tall" in {issue.code for issue in result.errors}


def test_orphan_heading_near_page_bottom_is_hard_failure(tmp_path):
    def build(page):
        page.insert_text((48, 45), "Alex Example", fontsize=16)
        page.insert_text((48, 67), "Software Developer", fontsize=12)
        for index in range(6):
            page.insert_text((48, 110 + index * 45), f"Evidence backed claim {index}", fontsize=BODY)
        page.insert_text((48, 750), "PROJECTS", fontsize=13)

    result = _evaluate(_save(build, tmp_path / "orphan.pdf"), claim_count=8)

    assert "visual_orphan_heading" in {issue.code for issue in result.errors}


def test_near_orphan_heading_with_small_body_block_warns(tmp_path):
    def build(page):
        page.insert_text((48, 45), "Alex Example", fontsize=16)
        page.insert_text((48, 67), "Software Developer", fontsize=12)
        for index in range(6):
            page.insert_text((48, 110 + index * 45), f"Evidence backed claim {index}", fontsize=BODY)
        page.insert_text((48, 710), "PROJECTS", fontsize=13)
        page.insert_text((48, 735), "Evidence backed claim 6", fontsize=BODY)

    result = _evaluate(_save(build, tmp_path / "near-orphan.pdf"), claim_count=9)
    error_codes = {issue.code for issue in result.errors}
    warning_codes = {issue.code for issue in result.warnings}

    assert "visual_orphan_heading" not in error_codes
    assert "visual_orphan_heading_warning" in warning_codes
