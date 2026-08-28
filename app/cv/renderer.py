from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import pt
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.cv.models import CVDocumentModel, RenderedCVArtifact, ValidationResult

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
    renderer_version = "ats-pdf-v1"

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

        story = self._build_story(document)
        doc = SimpleDocTemplate(
            str(temp),
            pagesize=A4,
            leftMargin=42,
            rightMargin=42,
            topMargin=36,
            bottomMargin=36,
            title="CV",
            author="",
        )
        doc.build(story, canvasmaker=DeterministicCanvas)

        payload = temp.read_bytes()
        sha256 = hashlib.sha256(payload).hexdigest()
        temp.replace(output)
        return RenderedCVArtifact(
            path=str(output),
            sha256=sha256,
            renderer_version=self.renderer_version,
        )

    def _build_story(self, document: CVDocumentModel) -> list[object]:
        body = ParagraphStyle(
            "CVBody",
            fontName="Helvetica",
            fontSize=9.5 * pt,
            leading=12 * pt,
            alignment=TA_LEFT,
            spaceAfter=3 * pt,
        )
        headline = ParagraphStyle(
            "CVHeadline",
            fontName="Helvetica-Bold",
            fontSize=11 * pt,
            leading=13 * pt,
            alignment=TA_LEFT,
            spaceAfter=3 * pt,
        )
        section = ParagraphStyle(
            "CVSection",
            fontName="Helvetica-Bold",
            fontSize=10.5 * pt,
            leading=12 * pt,
            alignment=TA_LEFT,
            spaceBefore=7 * pt,
            spaceAfter=3 * pt,
        )
        bullet = ParagraphStyle(
            "CVBullet",
            parent=body,
            leftIndent=10 * pt,
            firstLineIndent=-6 * pt,
        )

        claims_by_section = {
            name: [claim for claim in document.claims if claim.section == name]
            for name in SECTION_ORDER
        }

        story: list[object] = []
        for section_name in SECTION_ORDER:
            claims = claims_by_section[section_name]
            if not claims:
                continue

            if section_name != "headline":
                label = LABELS[document.language].get(section_name)
                if label:
                    story.append(Paragraph(escape(label), section))

            for claim in claims:
                style = headline if section_name == "headline" else body
                prefix = ""
                if claim.kind == "bullet":
                    style = bullet
                    prefix = "• "
                story.append(Paragraph(prefix + escape(claim.text), style))

            if section_name == "headline":
                story.append(Spacer(1, 4 * pt))

        return story
