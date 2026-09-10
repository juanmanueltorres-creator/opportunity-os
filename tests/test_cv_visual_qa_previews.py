from pathlib import Path

from app.cv.visual_models import VisualMetrics, VisualQAResult
from scripts import render_recruiter_previews as preview_script

_EXPECTED_PREVIEWS = {
    "recruiter_software__technical_clean.pdf",
    "recruiter_tech_operations__operations_clean.pdf",
    "recruiter_software__compact_ats.pdf",
}


class RecordingVisualQA:
    def __init__(self) -> None:
        self.profile_ids: list[str] = []

    def evaluate(
        self,
        render_result,
        recruiter_document,
        source_document,
        layout_profile,
        policy,
    ) -> VisualQAResult:
        self.profile_ids.append(layout_profile.id)
        return VisualQAResult(
            valid=True,
            metrics=VisualMetrics(
                page_count=1,
                content_bottom_ratio=0.75,
                largest_internal_gap_ratio=0.10,
                nonempty_line_count=20,
                lines_per_page_inch=2.5,
                max_text_block_lines=4,
                max_text_block_chars=120,
                headline_line_count=1,
                body_font_size=10.0,
                observed_font_size_levels=[10.0, 12.0],
            ),
        )


def test_preview_script_runs_visual_qa_for_each_layout(monkeypatch, tmp_path: Path) -> None:
    visual_qa = RecordingVisualQA()
    monkeypatch.setattr(preview_script, "VisualQualityQA", lambda: visual_qa)

    outputs = preview_script.render_previews(tmp_path)

    assert {path.name for path in outputs} == _EXPECTED_PREVIEWS
    assert visual_qa.profile_ids == [
        "technical_clean",
        "operations_clean",
        "compact_ats",
    ]


def test_preview_case_matrix_remains_exact() -> None:
    assert {
        f"{fixture_name}__{profile_id}.pdf"
        for fixture_name, profile_id in preview_script._PREVIEW_CASES
    } == _EXPECTED_PREVIEWS
