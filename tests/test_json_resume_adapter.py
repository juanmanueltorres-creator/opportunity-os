from __future__ import annotations

import importlib
import json

import pytest

from app.cv.models import CVClaim, CVDocumentModel, ClaimProvenance
from app.cv.recruiter_models import (
    RecruiterDocumentModel,
    RecruiterExperienceEntry,
    RecruiterProjectEntry,
    TechnologyGroup,
)


def _adapter():
    try:
        module = importlib.import_module("app.cv.adapters.json_resume")
    except ModuleNotFoundError as exc:
        if exc.name in {"app.cv.adapters", "app.cv.adapters.json_resume"}:
            pytest.fail("JSON Resume adapter is not implemented")
        raise
    return module.JSONResumeAdapter()


def _source_document() -> CVDocumentModel:
    claims = [
        CVClaim(
            claim_id="fact:name",
            section="headline",
            kind="identity",
            text="Alex Example",
        ),
        CVClaim(
            claim_id="fact:role",
            section="headline",
            kind="headline",
            text="Software & Operations Developer",
        ),
        CVClaim(
            claim_id="fact:email",
            section="headline",
            kind="contact",
            text="alex@example.test",
        ),
        CVClaim(
            claim_id="approved:summary",
            section="summary",
            kind="summary",
            text="Builds software and operational workflows.",
        ),
        CVClaim(
            claim_id="fact:python",
            section="skills",
            kind="skill",
            text="Python",
        ),
        CVClaim(
            claim_id="fact:sql",
            section="skills",
            kind="skill",
            text="SQL",
        ),
        CVClaim(
            claim_id="fact:project",
            section="projects",
            kind="project",
            text="Mapping Console",
        ),
        CVClaim(
            claim_id="approved:project-bullet",
            section="projects",
            kind="bullet",
            text="Auditable spatial workflows with deterministic map state.",
        ),
        CVClaim(
            claim_id="fact:employment",
            section="experience",
            kind="organization",
            text="Example Labs | 2024–Present",
        ),
        CVClaim(
            claim_id="approved:employment-bullet",
            section="experience",
            kind="bullet",
            text="Improved inventory and workflow visibility.",
        ),
        CVClaim(
            claim_id="fact:education",
            section="education",
            kind="education",
            text="BSc Applied Sciences",
        ),
        CVClaim(
            claim_id="fact:language",
            section="languages",
            kind="language",
            text="Spanish — Native",
        ),
        CVClaim(
            claim_id="fact:github",
            section="links",
            kind="link",
            text="github.com/example",
        ),
        CVClaim(
            claim_id="fact:hidden",
            section="summary",
            kind="summary",
            text="This unselected claim must never be exported.",
        ),
    ]
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=claims,
        entries=[],
        provenance_map={
            claim.claim_id: ClaimProvenance(fact_ids=[claim.claim_id])
            for claim in claims
        },
    )


def _recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
        contact_claim_ids=["fact:email"],
        profile_claim_ids=["approved:summary"],
        technology_groups=[
            TechnologyGroup(
                label_id="software_data",
                skill_claim_ids=["fact:python", "fact:sql"],
            )
        ],
        project_entries=[
            RecruiterProjectEntry(
                primary_claim_id="fact:project",
                bullet_claim_ids=["approved:project-bullet"],
            )
        ],
        experience_entries=[
            RecruiterExperienceEntry(
                primary_claim_id="fact:employment",
                bullet_claim_ids=["approved:employment-bullet"],
            )
        ],
        education_claim_ids=["fact:education"],
        language_claim_ids=["fact:language"],
        link_claim_ids=["fact:github"],
    )


def test_json_resume_adapter_maps_supported_recruiter_content() -> None:
    payload = _adapter().export(
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
    )

    assert payload == {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "meta": {"version": "v1.0.0"},
        "basics": {
            "name": "Alex Example",
            "label": "Software & Operations Developer",
            "email": "alex@example.test",
            "url": "https://github.com/example",
            "summary": "Builds software and operational workflows.",
        },
        "work": [
            {
                "name": "Example Labs | 2024–Present",
                "highlights": ["Improved inventory and workflow visibility."],
            }
        ],
        "education": [{"area": "BSc Applied Sciences"}],
        "skills": [
            {
                "name": "software_data",
                "keywords": ["Python", "SQL"],
            }
        ],
        "languages": [{"language": "Spanish — Native"}],
        "projects": [
            {
                "name": "Mapping Console",
                "highlights": [
                    "Auditable spatial workflows with deterministic map state."
                ],
            }
        ],
    }


def test_json_resume_export_is_independent_of_source_claim_order() -> None:
    adapter = _adapter()
    source = _source_document()
    reversed_source = source.model_copy(update={"claims": list(reversed(source.claims))})

    assert adapter.export(
        recruiter_document=_recruiter_document(),
        source_document=source,
    ) == adapter.export(
        recruiter_document=_recruiter_document(),
        source_document=reversed_source,
    )


def test_json_resume_adapter_never_exports_unselected_source_claims() -> None:
    payload = _adapter().export(
        recruiter_document=_recruiter_document(),
        source_document=_source_document(),
    )

    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "This unselected claim must never be exported." not in serialized


def test_json_resume_adapter_omits_empty_optional_sections() -> None:
    source = _source_document()
    recruiter = RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="fact:name",
        headline_claim_id="fact:role",
    )

    payload = _adapter().export(
        recruiter_document=recruiter,
        source_document=source,
    )

    assert payload == {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "meta": {"version": "v1.0.0"},
        "basics": {
            "name": "Alex Example",
            "label": "Software & Operations Developer",
        },
    }


def test_json_resume_adapter_fails_closed_on_missing_claim_reference() -> None:
    recruiter = _recruiter_document().model_copy(
        update={"identity_claim_id": "fact:missing"}
    )

    with pytest.raises(ValueError, match="JSON Resume export failed"):
        _adapter().export(
            recruiter_document=recruiter,
            source_document=_source_document(),
        )
