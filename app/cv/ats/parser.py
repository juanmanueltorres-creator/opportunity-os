from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Protocol

import pymupdf

from app.cv.ats.models import ParsedResume

LOCAL_RESUME_PARSER_VERSION = "local-pymupdf-sections-v1"

_SECTION_BY_HEADING = {
    "profile": "profile",
    "perfil": "profile",
    "technology": "technology",
    "tecnologia": "technology",
    "selected projects": "projects",
    "proyectos seleccionados": "projects",
    "experience": "experience",
    "experiencia": "experience",
    "education & training": "education",
    "educacion y formacion": "education",
    "languages": "languages",
    "idiomas": "languages",
    "links": "links",
    "enlaces": "links",
}


class ResumeParserAdapter(Protocol):
    def parse(self, pdf_path: str | Path) -> ParsedResume: ...


class LocalResumeParser:
    parser_version = LOCAL_RESUME_PARSER_VERSION

    def parse(self, pdf_path: str | Path) -> ParsedResume:
        try:
            document = pymupdf.open(pdf_path)
        except Exception as exc:
            raise ValueError("ATS resume parse failed") from exc

        try:
            lines: list[str] = []
            link_uris: list[str] = []
            for page in document:
                page_text = page.get_text("text")
                lines.extend(
                    line.strip()
                    for line in page_text.splitlines()
                    if line.strip()
                )
                for link in page.get_links():
                    uri = link.get("uri")
                    if isinstance(uri, str) and uri.strip():
                        normalized_uri = uri.strip()
                        if normalized_uri not in link_uris:
                            link_uris.append(normalized_uri)
        except Exception as exc:
            raise ValueError("ATS resume parse failed") from exc
        finally:
            document.close()

        if not lines:
            raise ValueError("ATS resume parse failed")

        first_section_index = next(
            (
                index
                for index, line in enumerate(lines)
                if _section_name(line) is not None
            ),
            len(lines),
        )
        preamble = lines[:first_section_index]

        sections: dict[str, list[str]] = {
            "profile": [],
            "technology": [],
            "projects": [],
            "experience": [],
            "education": [],
            "languages": [],
            "links": [],
        }
        current_section: str | None = None
        for line in lines[first_section_index:]:
            section = _section_name(line)
            if section is not None:
                current_section = section
                continue
            if current_section is not None:
                sections[current_section].append(line)

        return ParsedResume(
            parser_version=self.parser_version,
            identity=preamble[0] if preamble else None,
            headline=preamble[1] if len(preamble) > 1 else None,
            contacts=preamble[2:] if len(preamble) > 2 else [],
            profile=sections["profile"],
            technology=sections["technology"],
            projects=sections["projects"],
            experience=sections["experience"],
            education=sections["education"],
            languages=sections["languages"],
            links=sections["links"],
            link_uris=link_uris,
            extracted_text="\n".join(lines),
        )


def _section_name(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return _SECTION_BY_HEADING.get(" ".join(normalized.casefold().split()))
