from __future__ import annotations

import hashlib
import math
from html import escape
from pathlib import Path

import pymupdf
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.cv.layout import LayoutProfile
from app.cv.models import CVDocumentModel, RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.recruiter_policy import RecruiterPolicy

RENDERER_VERSION = "reportlab-human-v1"

_SECTION_LABELS = {
    "en": {
        "profile": "Profile",
        "technology": "Technology",
        "projects": "Selected Projects",
        "experience": "Experience",
        "education": "Education & Training",
        "languages": "Languages",
        "links": "Links",
    },
    "es": {
        "profile": "Perfil",
        "technology": "Tecnología",
        "projects": "Proyectos Seleccionados",
        "experience": "Experiencia",
        "education": "Educación y Formación",
        "languages": "Idiomas",
        "links": "Enlaces",
    },
}

_DENSITY = {
    "comfortable": {
        "body": 10.0,
        "leading": 12.2,
        "section_before": 7.0,
        "section_after": 3.5,
        "entry_after": 2.8,
    },
    "balanced": {
        "body": 9.7,
        "leading": 11.8,
        "section_before": 6.0,
        "section_after": 3.0,
        "entry_after": 2.4,
    },
    "compact": {
        "body": 9.4,
        "leading": 11.3,
        "section_before": 5.0,
        "section_after": 2.5,
        "entry_after": 2.0,
    },
}


class DeterministicHumanCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


class ReportLabHumanRenderer:
    """Optional human-first renderer over the canonical recruiter document.

    This renderer owns presentation only. It never composes candidate content and
    resolves every visible candidate string from claim IDs already selected by
    ``RecruiterDocumentModel``.
    """

    renderer_version = RENDERER_VERSION
    page_size = A4
    left_margin = 40
    right_margin = 40
    top_margin = 32
    bottom_margin = 34

    def render(
        self,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        output_path: str | Path,
        policy: RecruiterPolicy,
        layout_profile: LayoutProfile,
    ) -> RecruiterRenderResult:
        if recruiter_document.source_cv_document_version != source_document.document_version:
            raise ValueError("Human-first renderer source version mismatch")
        if recruiter_document.language != source_document.language:
            raise ValueError("Human-first renderer language mismatch")
        if layout_profile.ats_mode != "strict":
            raise ValueError("Human-first renderer requires ATS-safe layout")

        claims_by_id = {claim.claim_id: claim.text for claim in source_document.claims}
        selected_ids = recruiter_document.all_claim_ids()
        missing_ids = [claim_id for claim_id in selected_ids if claim_id not in claims_by_id]
        if missing_ids:
            raise ValueError("Human-first renderer references unknown claim")

        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".tmp.pdf")

        styles = self._styles(layout_profile)
        story = self._build_story(
            recruiter_document=recruiter_document,
            claims_by_id=claims_by_id,
            policy=policy,
            styles=styles,
        )

        document = SimpleDocTemplate(
            str(temporary),
            pagesize=self.page_size,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin,
            title="CV",
            author="",
            subject="",
            creator="Opportunity OS",
        )
        try:
            document.build(story, canvasmaker=DeterministicHumanCanvas)
            if not temporary.is_file():
                raise ValueError("Human-first renderer failed")
            temporary.replace(output)
            metrics = self._measure_pdf(
                output_path=output,
                headline_text=claims_by_id[recruiter_document.headline_claim_id],
                body_font_size=float(_DENSITY[layout_profile.density]["body"]),
            )
            payload = output.read_bytes()
        except ValueError:
            temporary.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            raise ValueError("Human-first renderer failed") from exc

        return RecruiterRenderResult(
            artifact=RenderedCVArtifact(
                path=str(output),
                sha256=hashlib.sha256(payload).hexdigest(),
                renderer_version=self.renderer_version,
            ),
            metrics=metrics,
        )

    def _styles(self, profile: LayoutProfile) -> dict[str, ParagraphStyle]:
        density = _DENSITY[profile.density]
        body_size = float(density["body"])
        leading = float(density["leading"])

        accent = HexColor("#173B57")
        text = HexColor("#222222")
        muted = HexColor("#4A4A4A")

        name_size = 18.0 if profile.density != "compact" else 17.0
        headline_size = 11.2 if profile.density == "comfortable" else 10.8
        section_size = 10.8 if profile.density != "compact" else 10.4

        body = ParagraphStyle(
            "HumanBody",
            fontName="Helvetica",
            fontSize=body_size,
            leading=leading,
            textColor=text,
            alignment=TA_LEFT,
            spaceAfter=float(density["entry_after"]),
        )
        return {
            "body": body,
            "name": ParagraphStyle(
                "HumanName",
                fontName="Helvetica-Bold",
                fontSize=name_size,
                leading=name_size + 2.0,
                textColor=accent,
                spaceAfter=1.5,
            ),
            "headline": ParagraphStyle(
                "HumanHeadline",
                fontName="Helvetica-Bold",
                fontSize=headline_size,
                leading=headline_size + 2.2,
                textColor=text,
                spaceAfter=2.0,
            ),
            "contact": ParagraphStyle(
                "HumanContact",
                fontName="Helvetica",
                fontSize=max(9.0, body_size - 0.3),
                leading=leading,
                textColor=muted,
                spaceAfter=1.0,
            ),
            "section": ParagraphStyle(
                "HumanSection",
                fontName="Helvetica-Bold",
                fontSize=section_size,
                leading=section_size + 2.0,
                textColor=accent,
                spaceBefore=float(density["section_before"]),
                spaceAfter=float(density["section_after"]),
                keepWithNext=True,
            ),
            "group": ParagraphStyle(
                "HumanGroup",
                parent=body,
                fontName="Helvetica-Bold",
                spaceAfter=1.5,
            ),
            "project_title": ParagraphStyle(
                "HumanProjectTitle",
                parent=body,
                fontName="Helvetica-Bold",
                fontSize=body_size + (0.35 if profile.emphasis == "technical" else 0.15),
                keepWithNext=True,
            ),
            "experience_title": ParagraphStyle(
                "HumanExperienceTitle",
                parent=body,
                fontName="Helvetica-Bold",
                fontSize=body_size + (0.35 if profile.emphasis == "experience" else 0.15),
                keepWithNext=True,
            ),
            "bullet": ParagraphStyle(
                "HumanBullet",
                parent=body,
                leftIndent=10,
                firstLineIndent=-6,
                bulletIndent=0,
                spaceAfter=max(1.4, float(density["entry_after"]) - 0.5),
            ),
        }

    def _build_story(
        self,
        *,
        recruiter_document: RecruiterDocumentModel,
        claims_by_id: dict[str, str],
        policy: RecruiterPolicy,
        styles: dict[str, ParagraphStyle],
    ) -> list[object]:
        language = recruiter_document.language
        labels = _SECTION_LABELS[language]
        text = lambda claim_id: claims_by_id[claim_id]
        paragraph = lambda claim_id, style: Paragraph(escape(text(claim_id)), style)

        story: list[object] = [
            paragraph(recruiter_document.identity_claim_id, styles["name"]),
            paragraph(recruiter_document.headline_claim_id, styles["headline"]),
        ]
        for claim_id in recruiter_document.contact_claim_ids:
            story.append(paragraph(claim_id, styles["contact"]))

        if recruiter_document.profile_claim_ids:
            self._section(story, labels["profile"], styles)
            for claim_id in recruiter_document.profile_claim_ids:
                story.append(paragraph(claim_id, styles["body"]))

        if recruiter_document.technology_groups:
            self._section(story, labels["technology"], styles)
            for group in recruiter_document.technology_groups:
                configured_group = policy.skill_groups.get(group.label_id)
                if configured_group is None:
                    raise ValueError("Human-first renderer references unknown skill group")
                group_label = configured_group.labels[language]
                skills = ", ".join(text(claim_id) for claim_id in group.skill_claim_ids)
                story.append(
                    Paragraph(
                        f"<b>{escape(group_label)}:</b> {escape(skills)}",
                        styles["body"],
                    )
                )

        project_entries = recruiter_document.project_entries
        if project_entries:
            self._section(story, labels["projects"], styles)
            for entry in project_entries:
                story.append(paragraph(entry.primary_claim_id, styles["project_title"]))
                for claim_id in entry.bullet_claim_ids:
                    story.append(
                        Paragraph(
                            escape(text(claim_id)),
                            styles["bullet"],
                            bulletText="•",
                        )
                    )
        elif recruiter_document.selected_project_claim_ids:
            self._section(story, labels["projects"], styles)
            for claim_id in recruiter_document.selected_project_claim_ids:
                story.append(paragraph(claim_id, styles["project_title"]))

        if recruiter_document.experience_entries:
            self._section(story, labels["experience"], styles)
            for entry in recruiter_document.experience_entries:
                story.append(paragraph(entry.primary_claim_id, styles["experience_title"]))
                for claim_id in entry.bullet_claim_ids:
                    story.append(
                        Paragraph(
                            escape(text(claim_id)),
                            styles["bullet"],
                            bulletText="•",
                        )
                    )

        if recruiter_document.education_claim_ids:
            self._section(story, labels["education"], styles)
            for claim_id in recruiter_document.education_claim_ids:
                story.append(paragraph(claim_id, styles["body"]))

        if recruiter_document.language_claim_ids:
            self._section(story, labels["languages"], styles)
            for claim_id in recruiter_document.language_claim_ids:
                story.append(paragraph(claim_id, styles["body"]))

        if recruiter_document.link_claim_ids:
            self._section(story, labels["links"], styles)
            for claim_id in recruiter_document.link_claim_ids:
                story.append(paragraph(claim_id, styles["body"]))

        return story

    @staticmethod
    def _section(
        story: list[object],
        label: str,
        styles: dict[str, ParagraphStyle],
    ) -> None:
        story.append(Paragraph(escape(label), styles["section"]))

    def _measure_pdf(
        self,
        *,
        output_path: Path,
        headline_text: str,
        body_font_size: float,
    ) -> RecruiterRenderMetrics:
        document = pymupdf.open(output_path)
        try:
            overflow_detected = False
            for page in document:
                tolerance = 0.5
                for block in page.get_text("blocks"):
                    x0, y0, x1, y1 = block[:4]
                    if (
                        x0 < -tolerance
                        or y0 < -tolerance
                        or x1 > page.rect.width + tolerance
                        or y1 > page.rect.height + tolerance
                    ):
                        overflow_detected = True

            available_width = (
                self.page_size[0] - self.left_margin - self.right_margin
            )
            headline_font_size = 11.2 if body_font_size >= 10.0 else 10.8
            estimated_width = stringWidth(
                headline_text,
                "Helvetica-Bold",
                headline_font_size,
            )
            headline_line_count = max(1, math.ceil(estimated_width / available_width))

            return RecruiterRenderMetrics(
                body_font_size=body_font_size,
                headline_line_count=headline_line_count,
                overflow_detected=overflow_detected,
            )
        finally:
            document.close()
