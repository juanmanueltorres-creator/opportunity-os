from __future__ import annotations

import re
from typing import Any

from app.cv.models import CVDocumentModel
from app.cv.recruiter_models import RecruiterDocumentModel

JSON_RESUME_SCHEMA_VERSION = "v1.0.0"
JSON_RESUME_SCHEMA_URL = (
    "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json"
)
JSON_RESUME_ADAPTER_VERSION = "json-resume-v1"

_EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$",
    re.IGNORECASE,
)
_WEB_URL_PATTERN = re.compile(
    r"^(?:https?://)?(?:www\.)?[A-Z0-9.-]+\.[A-Z]{2,}(?:/[^\s]*)?$",
    re.IGNORECASE,
)


class JSONResumeAdapter:
    adapter_version = JSON_RESUME_ADAPTER_VERSION

    def export(
        self,
        *,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
    ) -> dict[str, Any]:
        claims_by_id = {claim.claim_id: claim.text for claim in source_document.claims}

        def claim_text(claim_id: str) -> str:
            try:
                return claims_by_id[claim_id]
            except KeyError as exc:
                raise ValueError("JSON Resume export failed") from exc

        basics: dict[str, Any] = {
            "name": claim_text(recruiter_document.identity_claim_id),
            "label": claim_text(recruiter_document.headline_claim_id),
        }

        for claim_id in recruiter_document.contact_claim_ids:
            value = claim_text(claim_id).strip()
            if _EMAIL_PATTERN.fullmatch(value):
                basics["email"] = value
                break

        for claim_id in recruiter_document.link_claim_ids:
            value = claim_text(claim_id).strip()
            normalized = _normalize_url(value)
            if normalized is not None:
                basics["url"] = normalized
                break

        if recruiter_document.profile_claim_ids:
            basics["summary"] = "\n".join(
                claim_text(claim_id)
                for claim_id in recruiter_document.profile_claim_ids
            )

        payload: dict[str, Any] = {
            "$schema": JSON_RESUME_SCHEMA_URL,
            "meta": {"version": JSON_RESUME_SCHEMA_VERSION},
            "basics": basics,
        }

        if recruiter_document.experience_entries:
            work = []
            for entry in recruiter_document.experience_entries:
                item: dict[str, Any] = {"name": claim_text(entry.primary_claim_id)}
                if entry.bullet_claim_ids:
                    item["highlights"] = [
                        claim_text(claim_id) for claim_id in entry.bullet_claim_ids
                    ]
                work.append(item)
            payload["work"] = work

        if recruiter_document.education_claim_ids:
            payload["education"] = [
                {"area": claim_text(claim_id)}
                for claim_id in recruiter_document.education_claim_ids
            ]

        if recruiter_document.technology_groups:
            payload["skills"] = [
                {
                    "name": group.label_id,
                    "keywords": [
                        claim_text(claim_id) for claim_id in group.skill_claim_ids
                    ],
                }
                for group in recruiter_document.technology_groups
            ]

        if recruiter_document.language_claim_ids:
            payload["languages"] = [
                {"language": claim_text(claim_id)}
                for claim_id in recruiter_document.language_claim_ids
            ]

        projects = []
        if recruiter_document.project_entries:
            for entry in recruiter_document.project_entries:
                item = {"name": claim_text(entry.primary_claim_id)}
                if entry.bullet_claim_ids:
                    item["highlights"] = [
                        claim_text(claim_id) for claim_id in entry.bullet_claim_ids
                    ]
                projects.append(item)
        else:
            projects.extend(
                {"name": claim_text(claim_id)}
                for claim_id in recruiter_document.selected_project_claim_ids
            )
        if projects:
            payload["projects"] = projects

        return payload


def _normalize_url(value: str) -> str | None:
    if not _WEB_URL_PATTERN.fullmatch(value):
        return None
    if value.casefold().startswith(("http://", "https://")):
        return value
    return f"https://{value}"
