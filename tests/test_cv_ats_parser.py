from __future__ import annotations

import importlib
from pathlib import Path

import pymupdf
import pytest


def _parser():
    try:
        module = importlib.import_module("app.cv.ats.parser")
    except ModuleNotFoundError as exc:
        if exc.name == "app.cv.ats.parser":
            pytest.fail("ATS resume parser is not implemented")
        raise
    return module.LocalResumeParser()


def _write_pdf(path: Path, lines: list[str], *, uri: str | None = None) -> None:
    document = pymupdf.open()
    page = document.new_page()
    y = 72.0
    for line in lines:
        page.insert_text((72.0, y), line, fontsize=11)
        y += 18.0
    if uri is not None:
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(72.0, y, 300.0, y + 14.0),
                "uri": uri,
            }
        )
    document.save(path)
    document.close()


@pytest.mark.parametrize(
    ("headings", "expected_profile"),
    [
        (
            [
                "Profile",
                "Builds auditable systems.",
                "Technology",
                "Python, SQL",
                "Selected Projects",
                "Mapping Console",
                "Experience",
                "Example Labs | 2024-Present",
                "Education & Training",
                "BSc Applied Sciences",
                "Languages",
                "Spanish - Native",
                "Links",
                "github.com/example",
            ],
            "Builds auditable systems.",
        ),
        (
            [
                "Perfil",
                "Construye sistemas auditables.",
                "Tecnología",
                "Python, SQL",
                "Proyectos Seleccionados",
                "Consola de Mapas",
                "Experiencia",
                "Laboratorio Ejemplo | 2024-Presente",
                "Educación y Formación",
                "Ciencias Aplicadas",
                "Idiomas",
                "Español - Nativo",
                "Enlaces",
                "github.com/example",
            ],
            "Construye sistemas auditables.",
        ),
    ],
)
def test_local_parser_segments_renderer_sections_in_english_and_spanish(
    tmp_path: Path,
    headings: list[str],
    expected_profile: str,
) -> None:
    path = tmp_path / "resume.pdf"
    _write_pdf(
        path,
        [
            "Alex Example",
            "Software Developer",
            "alex@example.test",
            *headings,
        ],
    )

    parsed = _parser().parse(path)

    assert parsed.parser_version == "local-pymupdf-sections-v1"
    assert parsed.identity == "Alex Example"
    assert parsed.headline == "Software Developer"
    assert parsed.contacts == ["alex@example.test"]
    assert parsed.profile == [expected_profile]
    assert parsed.technology == ["Python, SQL"]
    assert parsed.experience
    assert parsed.education
    assert parsed.languages
    assert parsed.links == ["github.com/example"]


def test_local_parser_captures_pdf_uri_annotations(tmp_path: Path) -> None:
    path = tmp_path / "resume.pdf"
    _write_pdf(
        path,
        ["Alex Example", "Software Developer", "Links", "github.com/example"],
        uri="https://github.com/example",
    )

    parsed = _parser().parse(path)

    assert parsed.link_uris == ["https://github.com/example"]


def test_local_parser_fails_closed_for_empty_pdf(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    with pytest.raises(ValueError, match="ATS resume parse failed"):
        _parser().parse(path)


def test_local_parser_fails_closed_for_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not-a-pdf")

    with pytest.raises(ValueError, match="ATS resume parse failed"):
        _parser().parse(path)
