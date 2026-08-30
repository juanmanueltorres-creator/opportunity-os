from __future__ import annotations

import hashlib
import math
from html import escape
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from app.cv.models import (
    CVDocumentModel,
    RenderedCVArtifact,
    RenderLayoutMetrics,
    ValidationResult,
)

LABELS = {
    "en": {
        "summary": "Summary",
        "experience": "Experience",
        "projects": "Projects",
        "education": "Education",
        "skills": "Skills",
        "languages": "Languages",
        "links": "Links",
    },
    "es": {
        "summary": "Resumen",
        "experience": "Experiencia",
        "projects": "Proyectos",
        "education": "Educacion",
        "skills": "Habilidades",
        "languages": "Idiomas",
        "links": "Enlaces",
    },
}

SECTION_ORDER = (
    "headline",
    "summary",
    "skills",
    "experience",
    "projects",
    "education",
    "languages",
    "links",
)


class DeterministicCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


class ATSRenderer:
    renderer_version = "ats-pdf-v2"
    page_size = A4
    body_font_name = "Helvetica"
    bold_font_name = "Helvetica-Bold"
    body_font_size = 9.8
    name_font_size = 18.0
    role_font_size = 11.5
    section_font_size = 11.0
    metadata_font_size = 9.0
    max_pages = 2
    accent_hex = "#173B57"
    left_margin = 42
    right_margin = 42
    top_margin = 34
    bottom_margin = 36

    def __init__(self) -> None:
        self.layout_metrics: RenderLayoutMetrics | None = None

    def render(
        self,
        document: CVDocumentModel,
        validation: ValidationResult,
        output_path: str | Path,
    ) -> RenderedCVArtifact:
        claim_ids = {claim.claim_id for claim in document.claims}
        validated_ids = set(validation.validated_claim_ids)
        if not validation.valid or not claim_ids.issubset(validated_ids):
            raise ValueError("CVDocumentModel must be validated before rendering")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(".tmp.pdf")

        styles = self._styles()
        story = self._build_story(document, styles=styles)
        usable_width = self.page_size[0] - self.left_margin - self.right_margin
        usable_height = self.page_size[1] - self.top_margin - self.bottom_margin
        rendered_content_height = self._measure_story(
            story,
            usable_width=usable_width,
            usable_height=usable_height,
        )
        headline_line_count = self._measure_headline_lines(
            document,
            role_style=styles["role"],
            usable_width=usable_width,
            usable_height=usable_height,
        )

        doc = SimpleDocTemplate(
            str(temp),
            pagesize=self.page_size,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin,
            title="CV",
            author="",
        )
        doc.build(story, canvasmaker=DeterministicCanvas)

        self.layout_metrics = RenderLayoutMetrics(
            page_count=max(1, int(doc.page)),
            usable_height=usable_height,
            rendered_content_height=rendered_content_height,
            headline_line_count=headline_line_count,
            body_font_size=self.body_font_size,
        )

        payload = temp.read_bytes()
        sha256 = hashlib.sha256(payload).hexdigest()
        temp.replace(output)
        return RenderedCVArtifact(
            path=str(output),
            sha256=sha256,
            renderer_version=self.renderer_version,
        )

    def _styles(self) -> dict[str, ParagraphStyle]:
        accent = HexColor(self.accent_hex)
        body = ParagraphStyle(
            "CVBodyV2",
            fontName=self.body_font_name,
            fontSize=self.body_font_size,
            leading=12.8,
            textColor=HexColor("#222222"),
            alignment=TA_LEFT,
            spaceAfter=4,
        )
        return {
            "body": body,
            "name": ParagraphStyle(
                "CVNameV2",
                fontName=self.bold_font_name,
                fontSize=self.name_font_size,
                leading=20,
                textColor=accent,
                alignment=TA_LEFT,
                spaceAfter=2,
            ),
            "role": ParagraphStyle(
                "CVRoleV2",
                fontName=self.bold_font_name,
                fontSize=self.role_font_size,
                leading=14,
                textColor=accent,
                alignment=TA_LEFT,
                spaceAfter=3,
            ),
            "metadata": ParagraphStyle(
                "CVMetadataV2",
                fontName=self.body_font_name,
                fontSize=self.metadata_font_size,
                leading=11.5,
                textColor=HexColor("#444444"),
                alignment=TA_LEFT,
                spaceAfter=2,
            ),
            "section": ParagraphStyle(
                "CVSectionV2",
                fontName=self.bold_font_name,
                fontSize=self.section_font_size,
                leading=13,
                textColor=accent,
                alignment=TA_LEFT,
                spaceBefore=9,
                spaceAfter=4,
            ),
            "bullet": ParagraphStyle(
                "CVBulletV2",
                parent=body,
                leftIndent=11,
                firstLineIndent=-7,
                spaceAfter=3.5,
            ),
        }

    def _build_story(
        self,
        document: CVDocumentModel,
        *,
        styles: dict[str, ParagraphStyle] | None = None,
    ) -> list[object]:
        active_styles = styles or self._styles()
        accent = HexColor(self.accent_hex)
        claims_by_section = {
            section_name: [
                claim for claim in document.claims if claim.section == section_name
            ]
            for section_name in SECTION_ORDER
        }

        story: list[object] = []
        for section_name in SECTION_ORDER:
            claims = claims_by_section[section_name]
            if not claims:
                continue

            if section_name != "headline":
                label = LABELS[document.language].get(section_name)
                if label:
                    story.append(
                        Paragraph(escape(label).upper(), active_styles["section"])
                    )

            for claim in claims:
                style = active_styles["body"]
                prefix = ""
                if section_name == "headline":
                    if claim.kind == "identity":
                        style = active_styles["name"]
                    elif claim.kind == "headline":
                        style = active_styles["role"]
                    elif claim.kind in {"contact", "location", "link"}:
                        style = active_styles["metadata"]
                elif claim.kind == "bullet":
                    style = active_styles["bullet"]
                    prefix = "• "
                story.append(Paragraph(prefix + escape(claim.text), style))

            if section_name == "headline":
                story.append(Spacer(1, 4))
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.65,
                        color=accent,
                        spaceBefore=1,
                        spaceAfter=5,
                    )
                )

        return story

    @staticmethod
    def _measure_story(
        story: list[object],
        *,
        usable_width: float,
        usable_height: float,
    ) -> float:
        total = 0.0
        for flowable in story:
            _, height = flowable.wrap(usable_width, usable_height)
            before = float(getattr(flowable, "getSpaceBefore", lambda: 0)() or 0)
            after = float(getattr(flowable, "getSpaceAfter", lambda: 0)() or 0)
            total += float(height) + before + after
        return total

    @staticmethod
    def _measure_headline_lines(
        document: CVDocumentModel,
        *,
        role_style: ParagraphStyle,
        usable_width: float,
        usable_height: float,
    ) -> int:
        line_counts: list[int] = []
        for claim in document.claims:
            if claim.section != "headline" or claim.kind != "headline":
                continue
            paragraph = Paragraph(escape(claim.text), role_style)
            _, height = paragraph.wrap(usable_width, usable_height)
            line_counts.append(max(1, math.ceil(float(height) / role_style.leading)))
        return max(line_counts, default=0)
