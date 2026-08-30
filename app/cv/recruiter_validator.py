from __future__ import annotations

from app.cv.models import (
    CVClaim,
    CVDocumentModel,
    ValidationIssue,
    ValidationResult,
)
from app.cv.recruiter_models import RecruiterDocumentModel
from app.cv.recruiter_policy import RecruiterPolicy


def validate_recruiter_document(
    *,
    recruiter_document: RecruiterDocumentModel,
    source_document: CVDocumentModel,
    source_validation: ValidationResult,
    policy: RecruiterPolicy,
) -> ValidationResult:
    errors: list[ValidationIssue] = []

    if not source_validation.valid:
        errors.append(
            ValidationIssue(
                code="recruiter_source_validation_invalid",
                message="Recruiter document requires a valid semantic source document",
            )
        )

    if recruiter_document.source_cv_document_version != source_document.document_version:
        errors.append(
            ValidationIssue(
                code="recruiter_source_document_version_mismatch",
                message="Recruiter document source version does not match semantic document",
            )
        )

    claim_by_id = {claim.claim_id: claim for claim in source_document.claims}
    validated_ids = set(source_validation.validated_claim_ids)
    recruiter_ids = recruiter_document.all_claim_ids()

    accepted_ids: list[str] = []
    seen_accepted: set[str] = set()
    for claim_id in recruiter_ids:
        if claim_id not in claim_by_id:
            errors.append(
                ValidationIssue(
                    code="recruiter_unknown_claim_reference",
                    message="Recruiter document references a claim absent from semantic source",
                    claim_id=claim_id,
                )
            )
            continue
        if claim_id not in validated_ids:
            errors.append(
                ValidationIssue(
                    code="recruiter_unvalidated_claim_reference",
                    message="Recruiter document references a claim that did not pass semantic validation",
                    claim_id=claim_id,
                )
            )
            continue
        if claim_id not in seen_accepted:
            accepted_ids.append(claim_id)
            seen_accepted.add(claim_id)

    _validate_claim_roles(
        recruiter_document=recruiter_document,
        claim_by_id=claim_by_id,
        validated_ids=validated_ids,
        errors=errors,
    )
    _validate_group_labels(recruiter_document, policy, errors)
    _validate_policy_caps(recruiter_document, policy, errors)

    return ValidationResult(
        valid=not errors,
        errors=errors,
        warnings=[],
        validated_claim_ids=accepted_ids if not errors else [],
    )


def _validate_group_labels(
    document: RecruiterDocumentModel,
    policy: RecruiterPolicy,
    errors: list[ValidationIssue],
) -> None:
    allowed_labels = set(policy.skill_groups)
    for group in document.technology_groups:
        if group.label_id not in allowed_labels:
            errors.append(
                ValidationIssue(
                    code="recruiter_group_label_not_allowed",
                    message="Recruiter skill group label is not allowlisted by policy",
                )
            )


def _validate_policy_caps(
    document: RecruiterDocumentModel,
    policy: RecruiterPolicy,
    errors: list[ValidationIssue],
) -> None:
    if len(document.profile_claim_ids) > policy.max_profile_claims:
        errors.append(
            ValidationIssue(
                code="recruiter_profile_cap_exceeded",
                message="Recruiter profile exceeds configured claim cap",
            )
        )

    if len(document.technology_groups) > policy.max_skill_groups:
        errors.append(
            ValidationIssue(
                code="recruiter_skill_group_cap_exceeded",
                message="Recruiter document exceeds configured skill-group cap",
            )
        )

    skill_tokens = sum(
        len(group.skill_claim_ids) for group in document.technology_groups
    )
    if skill_tokens > policy.max_skill_tokens:
        errors.append(
            ValidationIssue(
                code="recruiter_skill_token_cap_exceeded",
                message="Recruiter document exceeds configured skill-token cap",
            )
        )

    project_count = (
        len(document.project_entries)
        if document.project_entries
        else len(document.selected_project_claim_ids)
    )
    if project_count > policy.max_projects:
        errors.append(
            ValidationIssue(
                code="recruiter_project_cap_exceeded",
                message="Recruiter document exceeds configured project cap",
            )
        )

    if len(document.experience_entries) > policy.max_experience_entries:
        errors.append(
            ValidationIssue(
                code="recruiter_experience_cap_exceeded",
                message="Recruiter document exceeds configured experience-entry cap",
            )
        )

    for entry in document.experience_entries:
        if len(entry.bullet_claim_ids) > policy.max_experience_bullets:
            errors.append(
                ValidationIssue(
                    code="recruiter_experience_bullet_cap_exceeded",
                    message="Recruiter experience entry exceeds configured bullet cap",
                    claim_id=entry.primary_claim_id,
                )
            )

    if len(document.education_claim_ids) > policy.max_education_items:
        errors.append(
            ValidationIssue(
                code="recruiter_education_cap_exceeded",
                message="Recruiter document exceeds configured education-item cap",
            )
        )


def _validate_claim_roles(
    *,
    recruiter_document: RecruiterDocumentModel,
    claim_by_id: dict[str, CVClaim],
    validated_ids: set[str],
    errors: list[ValidationIssue],
) -> None:
    _require_kind(
        recruiter_document.identity_claim_id,
        allowed={"identity"},
        role="identity",
        claim_by_id=claim_by_id,
        validated_ids=validated_ids,
        errors=errors,
    )
    _require_kind(
        recruiter_document.headline_claim_id,
        allowed={"headline"},
        role="headline",
        claim_by_id=claim_by_id,
        validated_ids=validated_ids,
        errors=errors,
    )

    for claim_id in recruiter_document.contact_claim_ids:
        _require_kind(
            claim_id,
            allowed={"contact", "location"},
            role="contact",
            claim_by_id=claim_by_id,
            validated_ids=validated_ids,
            errors=errors,
        )

    for claim_id in recruiter_document.profile_claim_ids:
        _require_kind(
            claim_id,
            allowed={"summary"},
            role="profile",
            claim_by_id=claim_by_id,
            validated_ids=validated_ids,
            errors=errors,
        )

    for group in recruiter_document.technology_groups:
        for claim_id in group.skill_claim_ids:
            _require_kind(
                claim_id,
                allowed={"skill"},
                role="skill",
                claim_by_id=claim_by_id,
                validated_ids=validated_ids,
                errors=errors,
            )

    if recruiter_document.project_entries:
        for entry in recruiter_document.project_entries:
            _require_kind(
                entry.primary_claim_id,
                allowed={"project"},
                role="project",
                claim_by_id=claim_by_id,
                validated_ids=validated_ids,
                errors=errors,
            )
            for claim_id in entry.bullet_claim_ids:
                _require_kind(
                    claim_id,
                    allowed={"bullet"},
                    role="project_bullet",
                    claim_by_id=claim_by_id,
                    validated_ids=validated_ids,
                    errors=errors,
                )
    else:
        for claim_id in recruiter_document.selected_project_claim_ids:
            _require_kind(
                claim_id,
                allowed={"project"},
                role="project",
                claim_by_id=claim_by_id,
                validated_ids=validated_ids,
                errors=errors,
            )

    for entry in recruiter_document.experience_entries:
        _require_kind(
            entry.primary_claim_id,
            allowed={"organization", "title", "date"},
            role="experience",
            claim_by_id=claim_by_id,
            validated_ids=validated_ids,
            errors=errors,
        )
        for claim_id in entry.bullet_claim_ids:
            _require_kind(
                claim_id,
                allowed={"bullet"},
                role="experience_bullet",
                claim_by_id=claim_by_id,
                validated_ids=validated_ids,
                errors=errors,
            )

    for claim_id in recruiter_document.education_claim_ids:
        _require_kind(
            claim_id,
            allowed={"education"},
            role="education",
            claim_by_id=claim_by_id,
            validated_ids=validated_ids,
            errors=errors,
        )

    for claim_id in recruiter_document.language_claim_ids:
        _require_kind(
            claim_id,
            allowed={"language"},
            role="language",
            claim_by_id=claim_by_id,
            validated_ids=validated_ids,
            errors=errors,
        )

    for claim_id in recruiter_document.link_claim_ids:
        _require_kind(
            claim_id,
            allowed={"link"},
            role="link",
            claim_by_id=claim_by_id,
            validated_ids=validated_ids,
            errors=errors,
        )


def _require_kind(
    claim_id: str,
    *,
    allowed: set[str],
    role: str,
    claim_by_id: dict[str, CVClaim],
    validated_ids: set[str],
    errors: list[ValidationIssue],
) -> None:
    claim = claim_by_id.get(claim_id)
    if claim is None or claim_id not in validated_ids:
        return
    if claim.kind not in allowed:
        errors.append(
            ValidationIssue(
                code="recruiter_claim_role_mismatch",
                message=f"Validated claim kind is not allowed for recruiter role: {role}",
                claim_id=claim_id,
            )
        )
