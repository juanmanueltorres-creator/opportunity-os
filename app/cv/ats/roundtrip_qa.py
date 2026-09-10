from __future__ import annotations

import re
from collections.abc import Iterable

from app.cv.ats.models import ATSCategoryRecovery, ATSRoundTripQAResult, ParsedResume
from app.cv.ats.policy import ATSRoundTripPolicy
from app.cv.models import CVDocumentModel, ValidationIssue
from app.cv.recruiter_models import RecruiterDocumentModel

_ERROR_CODES = {
    "identity": "ats_roundtrip_identity_missing",
    "contact": "ats_roundtrip_contact_recovery_low",
    "experience": "ats_roundtrip_experience_recovery_low",
    "skills": "ats_roundtrip_skill_recovery_low",
    "education": "ats_roundtrip_education_recovery_low",
    "links": "ats_roundtrip_link_recovery_low",
}


class ATSRoundTripQA:
    def evaluate(
        self,
        *,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        parsed_resume: ParsedResume,
        policy: ATSRoundTripPolicy,
    ) -> ATSRoundTripQAResult:
        claims_by_id = {claim.claim_id: claim.text for claim in source_document.claims}

        expected_by_category = {
            "identity": [
                recruiter_document.identity_claim_id,
                recruiter_document.headline_claim_id,
            ],
            "contact": list(recruiter_document.contact_claim_ids),
            "experience": [
                entry.primary_claim_id
                for entry in recruiter_document.experience_entries
            ],
            "skills": [
                claim_id
                for group in recruiter_document.technology_groups
                for claim_id in group.skill_claim_ids
            ],
            "education": list(recruiter_document.education_claim_ids),
            "links": list(recruiter_document.link_claim_ids),
        }

        parsed_by_category = {
            "identity": [parsed_resume.identity, parsed_resume.headline],
            "contact": parsed_resume.contacts,
            "experience": parsed_resume.experience,
            "skills": parsed_resume.technology,
            "education": parsed_resume.education,
            "links": [*parsed_resume.links, *parsed_resume.link_uris],
        }

        thresholds = {
            "identity": policy.thresholds.identity,
            "contact": policy.thresholds.contact,
            "experience": policy.thresholds.experience,
            "skills": policy.thresholds.skills,
            "education": policy.thresholds.education,
            "links": policy.thresholds.links,
        }

        categories: dict[str, ATSCategoryRecovery] = {}
        errors: list[ValidationIssue] = []
        aggregate_ratios: list[float] = []

        for category in (
            "identity",
            "contact",
            "experience",
            "skills",
            "education",
            "links",
        ):
            expected_ids = expected_by_category[category]
            candidate_text = _normalize_zone(parsed_by_category[category])
            recovered_ids: list[str] = []

            for claim_id in expected_ids:
                try:
                    expected_text = claims_by_id[claim_id]
                except KeyError as exc:
                    raise ValueError("ATS round-trip QA failed") from exc
                normalized_expected = _normalize(expected_text)
                if normalized_expected and normalized_expected in candidate_text:
                    recovered_ids.append(claim_id)

            ratio = (
                len(recovered_ids) / len(expected_ids)
                if expected_ids
                else 1.0
            )
            categories[category] = ATSCategoryRecovery(
                expected_claim_ids=expected_ids,
                recovered_claim_ids=recovered_ids,
                recovery_ratio=ratio,
            )

            if expected_ids:
                aggregate_ratios.append(ratio)
            if ratio < thresholds[category]:
                errors.append(
                    ValidationIssue(
                        code=_ERROR_CODES[category],
                        message=f"ATS round-trip recovery below threshold for {category}",
                    )
                )

        aggregate = (
            sum(aggregate_ratios) / len(aggregate_ratios)
            if aggregate_ratios
            else 1.0
        )
        return ATSRoundTripQAResult(
            valid=not errors,
            parser_version=parsed_resume.parser_version,
            policy_version=policy.version,
            categories=categories,
            aggregate_recovery_ratio=aggregate,
            errors=errors,
            warnings=[],
        )


def _normalize_zone(values: Iterable[str | None]) -> str:
    return _normalize(" ".join(value for value in values if value))


def _normalize(value: str) -> str:
    normalized = value.replace("\u00ad", "")
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = " ".join(normalized.split()).casefold()
    return re.sub(r"\s*-\s*", "-", normalized)
