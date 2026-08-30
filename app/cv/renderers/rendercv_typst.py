from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import fitz
import yaml

from app.cv.models import CVDocumentModel, RenderedCVArtifact
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterRenderMetrics,
    RecruiterRenderResult,
)
from app.cv.recruiter_policy import RecruiterPolicy

RENDERER_VERSION = "rendercv-typst-v1"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DESIGN_PATH = _PROJECT_ROOT / "config" / "rendercv_one_page.yaml"
_FONTAWESOME_STUB_PATH = _PROJECT_ROOT / "config" / "typst_fontawesome_stub"
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


class RenderCVTypstRenderer:
    renderer_version = RENDERER_VERSION

    def __init__(self, design_path: str | Path | None = None) -> None:
        self.design_path = Path(design_path) if design_path else _DEFAULT_DESIGN_PATH

    def render(
        self,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        output_path: str | Path,
        policy: RecruiterPolicy,
    ) -> RecruiterRenderResult:
        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        design = self.design_path.resolve()

        try:
            payload = _build_rendercv_payload(
                recruiter_document=recruiter_document,
                source_document=source_document,
                policy=policy,
            )
            body_font_size = _configured_body_font_size(design)

            with tempfile.TemporaryDirectory(
                prefix="opportunity-os-rendercv-",
                dir=output.parent,
            ) as temporary_directory:
                temporary_path = Path(temporary_directory)
                input_path = temporary_path / "cv.yaml"
                input_path.write_text(
                    yaml.safe_dump(
                        payload,
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                command = [
                    "rendercv",
                    "render",
                    str(input_path),
                    "--design",
                    str(design),
                    "--pdf-path",
                    str(output),
                    "--dont-generate-markdown",
                    "--dont-generate-html",
                    "--dont-generate-png",
                    "--quiet",
                ]
                completed = subprocess.run(
                    command,
                    cwd=temporary_path,
                    check=False,
                    capture_output=True,
                    text=True,
                    shell=False,
                )
                if completed.returncode != 0 or not output.is_file():
                    raise ValueError("RenderCV/Typst render failed")

            metrics = _measure_pdf(
                output_path=output,
                headline_text=_claim_text(
                    source_document,
                    recruiter_document.headline_claim_id,
                ),
                body_font_size=body_font_size,
            )
            artifact = RenderedCVArtifact(
                path=str(output),
                sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                renderer_version=self.renderer_version,
            )
            return RecruiterRenderResult(artifact=artifact, metrics=metrics)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("RenderCV/Typst render failed") from exc


def _prepare_rendercv_offline_package_path() -> Path:
    from rendercv.renderer.pdf_png import get_package_path

    package_path = get_package_path()
    target = package_path / "preview" / "fontawesome" / "0.6.0"
    target.mkdir(parents=True, exist_ok=True)

    for filename in ("typst.toml", "lib.typ"):
        source = _FONTAWESOME_STUB_PATH / filename
        if not source.is_file():
            raise ValueError("RenderCV/Typst render failed")
        shutil.copyfile(source, target / filename)

    return package_path


def _build_rendercv_payload(
    *,
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
    policy: RecruiterPolicy,
) -> dict[str, Any]:
    language = recruiter_document.language
    labels = _SECTION_LABELS[language]
    claim_text = lambda claim_id: _escape_markdown(
        _claim_text(source_document, claim_id)
    )

    custom_connections = [
        {
            "fontawesome_icon": "envelope",
            "placeholder": claim_text(claim_id),
            "url": None,
        }
        for claim_id in recruiter_document.contact_claim_ids
    ]

    sections: dict[str, list[Any]] = {}

    if recruiter_document.profile_claim_ids:
        sections[labels["profile"]] = [
            claim_text(claim_id)
            for claim_id in recruiter_document.profile_claim_ids
        ]

    if recruiter_document.technology_groups:
        technology_entries = []
        for group in recruiter_document.technology_groups:
            configured_group = policy.skill_groups.get(group.label_id)
            if configured_group is None:
                raise ValueError("RenderCV/Typst render failed")
            group_label = configured_group.labels[language]
            technology_entries.append(
                {
                    "label": group_label,
                    "details": ", ".join(
                        claim_text(claim_id)
                        for claim_id in group.skill_claim_ids
                    ),
                }
            )
        sections[labels["technology"]] = technology_entries

    if recruiter_document.selected_project_claim_ids:
        sections[labels["projects"]] = [
            claim_text(claim_id)
            for claim_id in recruiter_document.selected_project_claim_ids
        ]

    if recruiter_document.experience_entries:
        sections[labels["experience"]] = [
            {
                "name": claim_text(entry.primary_claim_id),
                "highlights": [
                    claim_text(claim_id) for claim_id in entry.bullet_claim_ids
                ]
                or None,
            }
            for entry in recruiter_document.experience_entries
        ]

    if recruiter_document.education_claim_ids:
        sections[labels["education"]] = [
            claim_text(claim_id)
            for claim_id in recruiter_document.education_claim_ids
        ]

    if recruiter_document.language_claim_ids:
        sections[labels["languages"]] = [
            claim_text(claim_id)
            for claim_id in recruiter_document.language_claim_ids
        ]

    if recruiter_document.link_claim_ids:
        sections[labels["links"]] = [
            claim_text(claim_id)
            for claim_id in recruiter_document.link_claim_ids
        ]

    return {
        "cv": {
            "name": claim_text(recruiter_document.identity_claim_id),
            "headline": claim_text(recruiter_document.headline_claim_id),
            "custom_connections": custom_connections or None,
            "sections": sections or None,
        },
        "settings": {
            "current_date": "2000-01-01",
            "pdf_title": "CV",
            "bold_keywords": [],
        },
    }


def _claim_text(source_document: CVDocumentModel, claim_id: str) -> str:
    claim_by_id = {claim.claim_id: claim for claim in source_document.claims}
    try:
        return claim_by_id[claim_id].text
    except KeyError as exc:
        raise ValueError("RenderCV/Typst render failed") from exc


def _escape_markdown(text: str) -> str:
    escaped = text.replace("\\", "\\\\")
    for character in ("*", "_", "`", "[", "]", "#"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _configured_body_font_size(design_path: Path) -> float:
    payload = yaml.safe_load(design_path.read_text(encoding="utf-8"))
    value = payload["design"]["typography"]["font_size"]["body"]
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)pt\s*", str(value))
    if match is None:
        raise ValueError("RenderCV/Typst render failed")
    return float(match.group(1))


def _measure_pdf(
    *,
    output_path: Path,
    headline_text: str,
    body_font_size: float,
) -> RecruiterRenderMetrics:
    document = fitz.open(output_path)
    try:
        overflow_detected = False
        headline_line_count = 0

        for page_index, page in enumerate(document):
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

            if page_index == 0:
                headline_line_count = len(page.search_for(headline_text))

        return RecruiterRenderMetrics(
            body_font_size=body_font_size,
            headline_line_count=headline_line_count,
            overflow_detected=overflow_detected,
        )
    finally:
        document.close()
