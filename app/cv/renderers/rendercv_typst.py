from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pymupdf as fitz
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
_EMAIL_PATTERN = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.IGNORECASE,
)
_WEB_URL_PATTERN = re.compile(
    r"(?P<url>https?://[^\s|]+|(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s|]*)?)"
)
_TRAILING_URL_PUNCTUATION = ".,);]}>"
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
                input_yaml = yaml.safe_dump(
                    payload,
                    allow_unicode=True,
                    sort_keys=False,
                )
                input_path.write_text(input_yaml, encoding="utf-8")

                _render_pdf_in_process(
                    input_yaml=input_yaml,
                    input_path=input_path,
                    design_path=design,
                    temporary_path=temporary_path,
                    output_path=output,
                )
                if not output.is_file():
                    raise ValueError("RenderCV/Typst render failed")

            _insert_clickable_links(
                output_path=output,
                recruiter_document=recruiter_document,
                source_document=source_document,
            )
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
            return RecruiterRenderResult(
                artifact=artifact,
                metrics=metrics,
            )
        except Exception:
            output.unlink(missing_ok=True)
            raise


def _render_pdf_in_process(
    *,
    input_yaml: str,
    input_path: Path,
    design_path: Path,
    temporary_path: Path,
    output_path: Path,
) -> None:
    try:
        from rendercv.cli import create_a_new_data_model
        from rendercv.renderer import generate_pdf
    except ImportError as exc:  # pragma: no cover - packaging/runtime guard
        raise ValueError("RenderCV runtime is unavailable") from exc

    command = [
        "rendercv",
        "render",
        str(input_path),
        "--design",
        str(design_path),
        "--pdf-path",
        str(output_path),
        "--dont-generate-html",
        "--dont-generate-markdown",
        "--dont-generate-png",
    ]
    data_model, _, _, _ = create_a_new_data_model(input_yaml, command)

    fontawesome_stub = _prepare_fontawesome_stub(temporary_path)
    packages_path = temporary_path / "typst-packages"
    package_target = packages_path / "preview" / "fontawesome" / "0.6.0"
    package_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fontawesome_stub, package_target)

    original_packages_path = __import__("os").environ.get("TYPST_PACKAGE_PATH")
    __import__("os").environ["TYPST_PACKAGE_PATH"] = str(packages_path)
    try:
        generated_pdf = generate_pdf(data_model, temporary_path)
    finally:
        if original_packages_path is None:
            __import__("os").environ.pop("TYPST_PACKAGE_PATH", None)
        else:
            __import__("os").environ["TYPST_PACKAGE_PATH"] = original_packages_path

    generated = Path(generated_pdf)
    if generated.resolve() != output_path.resolve():
        shutil.copy2(generated, output_path)


def _prepare_fontawesome_stub(temporary_path: Path) -> Path:
    if not _FONTAWESOME_STUB_PATH.is_dir():
        raise ValueError("RenderCV FontAwesome stub is unavailable")
    destination = temporary_path / "fontawesome-stub"
    shutil.copytree(_FONTAWESOME_STUB_PATH, destination)
    return destination


def _insert_clickable_links(
    *,
    output_path: Path,
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
) -> None:
    claim_by_id = source_document.claim_by_id()
    targets: list[tuple[str, str]] = []
    candidate_ids = [
        *recruiter_document.contact_claim_ids,
        *recruiter_document.link_claim_ids,
    ]
    for claim_id in candidate_ids:
        claim = claim_by_id.get(claim_id)
        if claim is None:
            continue
        target = _claim_link_target(claim.text)
        if target is not None:
            targets.append((claim.text, target))

    if not targets:
        return

    document = fitz.open(output_path)
    try:
        inserted = False
        for page in document:
            for visible_text, target in targets:
                for rectangle in page.search_for(visible_text):
                    page.insert_link(
                        {
                            "kind": fitz.LINK_URI,
                            "from": rectangle,
                            "uri": target,
                        }
                    )
                    inserted = True
        if inserted:
            document.save(
                output_path,
                incremental=True,
                encryption=fitz.PDF_ENCRYPT_KEEP,
                no_new_id=True,
            )
    finally:
        document.close()


def _claim_link_target(text: str) -> str | None:
    value = text.strip()
    email_match = _EMAIL_PATTERN.fullmatch(value)
    if email_match is not None:
        return f"mailto:{email_match.group(0)}"

    url_match = _WEB_URL_PATTERN.fullmatch(value)
    if url_match is None:
        return None
    url = url_match.group("url").rstrip(_TRAILING_URL_PUNCTUATION)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://{url}"


def _measure_pdf(
    *,
    output_path: Path,
    headline_text: str,
    body_font_size: float,
) -> RecruiterRenderMetrics:
    document = fitz.open(output_path)
    try:
        if len(document) == 0:
            return RecruiterRenderMetrics(
                page_count=0,
                body_font_size=body_font_size,
                headline_line_count=0,
                usable_height=1.0,
                rendered_content_height=0.0,
            )

        headline_line_count = 0
        min_y = None
        max_y = None
        for page in document:
            for block in page.get_text("blocks"):
                if len(block) < 5:
                    continue
                x0, y0, x1, y1, text = block[:5]
                del x0, x1
                if str(text).strip():
                    min_y = float(y0) if min_y is None else min(min_y, float(y0))
                    max_y = float(y1) if max_y is None else max(max_y, float(y1))
            headline_line_count += len(page.search_for(headline_text))

        page_height = float(document[0].rect.height)
        rendered_content_height = 0.0
        if min_y is not None and max_y is not None:
            rendered_content_height = max(0.0, max_y - min_y)
        return RecruiterRenderMetrics(
            page_count=len(document),
            body_font_size=body_font_size,
            headline_line_count=max(1, headline_line_count) if headline_text else 0,
            usable_height=page_height,
            rendered_content_height=rendered_content_height,
        )
    finally:
        document.close()


def _configured_body_font_size(design_path: Path) -> float:
    payload = yaml.safe_load(design_path.read_text(encoding="utf-8")) or {}
    typography = payload.get("design", {}).get("typography", {})
    raw = typography.get("font_size", {}).get("body", "10pt")
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*pt\s*", str(raw))
    if match is None:
        raise ValueError("RenderCV body font size must be configured in pt")
    return float(match.group(1))


def _build_rendercv_payload(
    *,
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
    policy: RecruiterPolicy,
) -> dict[str, Any]:
    claim_by_id = source_document.claim_by_id()
    language = source_document.language if source_document.language in _SECTION_LABELS else "en"
    labels = _SECTION_LABELS[language]

    sections: dict[str, list[Any]] = {}

    profile_claims = _claim_texts(claim_by_id, recruiter_document.summary_claim_ids)
    if profile_claims:
        sections[labels["profile"]] = [" ".join(profile_claims)]

    technology_entries: list[str] = []
    for group in recruiter_document.technology_groups:
        values = _claim_texts(claim_by_id, group.skill_claim_ids)
        if values:
            technology_entries.append(f"{group.label}: {', '.join(values)}")
    if technology_entries:
        sections[labels["technology"]] = technology_entries

    project_entries: list[dict[str, Any]] = []
    for entry in recruiter_document.project_entries:
        name = _claim_text(claim_by_id, entry.project_claim_id)
        bullets = _claim_texts(claim_by_id, entry.bullet_claim_ids)
        if not bullets:
            bullets = [name]
        project_entries.append(
            {
                "name": name,
                "highlights": bullets,
            }
        )
    if project_entries:
        sections[labels["projects"]] = project_entries

    experience_entries: list[dict[str, Any]] = []
    for entry in recruiter_document.experience_entries:
        title = _claim_text(claim_by_id, entry.employment_claim_id)
        bullets = _claim_texts(claim_by_id, entry.bullet_claim_ids)
        if not bullets:
            bullets = [title]
        experience_entries.append(
            {
                "position": title,
                "company": "",
                "highlights": bullets,
            }
        )
    if experience_entries:
        sections[labels["experience"]] = experience_entries

    education_claims = _claim_texts(claim_by_id, recruiter_document.education_claim_ids)
    if education_claims:
        sections[labels["education"]] = education_claims

    language_claims = _claim_texts(claim_by_id, recruiter_document.language_claim_ids)
    if language_claims:
        sections[labels["languages"]] = language_claims

    link_claims = _claim_texts(claim_by_id, recruiter_document.link_claim_ids)
    if link_claims:
        sections[labels["links"]] = link_claims

    connections = _claim_texts(claim_by_id, recruiter_document.contact_claim_ids)
    if len(connections) > policy.max_contact_items:
        connections = connections[: policy.max_contact_items]

    return {
        "cv": {
            "name": _claim_text(claim_by_id, recruiter_document.name_claim_id),
            "headline": _claim_text(claim_by_id, recruiter_document.headline_claim_id),
            "location": None,
            "email": None,
            "phone": None,
            "website": None,
            "social_networks": [],
            "custom_connections": [
                {"placeholder": connection, "fontawesome_icon": ""}
                for connection in connections
            ],
            "sections": sections,
        },
        "design": str(_DEFAULT_DESIGN_PATH),
        "locale": {
            "language": "english" if language == "en" else "spanish",
        },
        "settings": {
            "current_date": "2026-01-01",
            "render_command": {
                "dont_generate_html": True,
                "dont_generate_markdown": True,
                "dont_generate_png": True,
            },
        },
    }


def _claim_text(claim_by_id: dict, claim_id: str) -> str:
    claim = claim_by_id.get(claim_id)
    if claim is None:
        raise ValueError(f"Missing approved claim for recruiter renderer: {claim_id}")
    return claim.text


def _claim_texts(claim_by_id: dict, claim_ids: list[str]) -> list[str]:
    return [_claim_text(claim_by_id, claim_id) for claim_id in claim_ids]
