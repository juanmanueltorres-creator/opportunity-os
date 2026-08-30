from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.cv.layout_qa import LayoutQA
from app.cv.models import RenderedCVArtifact, RenderLayoutMetrics


def _pdf(path: Path, *, text: str = "Visible CV text", pages: int = 1) -> RenderedCVArtifact:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    for index in range(pages):
        if text:
            pdf.drawString(72, 720, f"{text} {index + 1}")
        pdf.showPage()
    pdf.save()
    return RenderedCVArtifact(
        path=str(path),
        sha256="0" * 64,
        renderer_version="ats-pdf-v2",
    )


def _metrics(
    *,
    page_count: int = 1,
    ratio: float = 0.75,
    headline_line_count: int = 1,
    body_font_size: float = 9.8,
) -> RenderLayoutMetrics:
    usable = 700.0
    return RenderLayoutMetrics(
        page_count=page_count,
        usable_height=usable,
        rendered_content_height=usable * ratio,
        headline_line_count=headline_line_count,
        body_font_size=body_font_size,
    )


def test_low_utilization_is_warning_not_error(tmp_path: Path) -> None:
    result = LayoutQA().evaluate(
        _pdf(tmp_path / "low.pdf"),
        _metrics(ratio=0.50),
    )

    assert result.valid is True
    assert result.used_height_ratio == 0.50
    assert [warning.code for warning in result.warnings] == [
        "layout_low_utilization"
    ]
    assert result.errors == []


def test_high_utilization_is_warning_not_error(tmp_path: Path) -> None:
    result = LayoutQA().evaluate(
        _pdf(tmp_path / "high.pdf"),
        _metrics(ratio=0.97),
    )

    assert result.valid is True
    assert "layout_high_utilization" in {warning.code for warning in result.warnings}


def test_more_than_two_pages_is_hard_error(tmp_path: Path) -> None:
    result = LayoutQA().evaluate(
        _pdf(tmp_path / "three.pdf", pages=3),
        _metrics(page_count=3),
    )

    assert result.valid is False
    assert "layout_page_count_exceeded" in {error.code for error in result.errors}


def test_missing_extractable_text_is_hard_error(tmp_path: Path) -> None:
    result = LayoutQA().evaluate(
        _pdf(tmp_path / "empty.pdf", text=""),
        _metrics(),
        expected_nonempty=True,
    )

    assert result.valid is False
    assert "layout_missing_extractable_text" in {
        error.code for error in result.errors
    }


def test_headline_wrap_is_warning(tmp_path: Path) -> None:
    result = LayoutQA().evaluate(
        _pdf(tmp_path / "wrap.pdf"),
        _metrics(headline_line_count=3),
    )

    assert result.valid is True
    assert "layout_headline_wrap" in {warning.code for warning in result.warnings}


def test_body_font_below_nine_points_is_hard_error(tmp_path: Path) -> None:
    result = LayoutQA().evaluate(
        _pdf(tmp_path / "tiny.pdf"),
        _metrics(body_font_size=8.9),
    )

    assert result.valid is False
    assert "layout_body_font_too_small" in {error.code for error in result.errors}
