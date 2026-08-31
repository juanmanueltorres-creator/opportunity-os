from __future__ import annotations

import re

from app.cv.models import (
    CVDocumentModel,
    EvidenceCatalogSnapshot,
    EvidenceSelection,
    MasterFact,
    MasterFactsSnapshot,
    ValidationIssue,
    ValidationResult,
)

_NUMBER_RE = re.compile(r"(?<![A-Za-z])(?!(?:2|3)[Dd]\b)\d+(?:[.,]\d+)?%?")
_EXACT_FACT_KINDS = {"organization", "title", "date"}


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def validate_cv(
    *,
    document: CVDocumentModel,
    master_facts: MasterFactsSnapshot,
    evidence_catalog: EvidenceCatalogSnapshot,
    application_track_id: str,
    selection: EvidenceSelection,
) -> ValidationResult:
    fact_by_id = {fact.id: fact for fact in master_facts.facts}
    module_by_id = {module.id: module for module in evidence_catalog.modules}
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = [
        ValidationIssue(
            code="unsupported_requirement",
            message=requirement,
        )
        for requirement in selection.unsupported_requirements
    ]
    validated_claim_ids: list[str] = []

    for claim in document.claims:
        provenance = document.provenance_map.get(claim.claim_id)
        if provenance is None:
            errors.append(
                ValidationIssue(
                    code="missing_provenance",
                    message="Visible claim has no provenance",
                    claim_id=claim.claim_id,
                )
            )
            continue

        claim_has_error = False
        referenced_facts: list[MasterFact] = []
        for fact_id in provenance.fact_ids:
            fact = fact_by_id.get(fact_id)
            if fact is None:
                errors.append(
                    ValidationIssue(
                        code="missing_fact",
                        message="Claim references a missing fact",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True
                continue
            referenced_facts.append(fact)
            if not fact.verified:
                errors.append(
                    ValidationIssue(
                        code="unverified_fact",
                        message="Claim references an unverified fact",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True
            if application_track_id not in fact.track_ids:
                errors.append(
                    ValidationIssue(
                        code="cross_track_fact",
                        message="Claim references a fact outside the application track",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True

        referenced_modules = []
        for evidence_id in provenance.evidence_ids:
            module = module_by_id.get(evidence_id)
            if module is None:
                errors.append(
                    ValidationIssue(
                        code="missing_evidence",
                        message="Claim references missing evidence",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True
                continue
            referenced_modules.append(module)
            if not module.verified:
                errors.append(
                    ValidationIssue(
                        code="unverified_evidence",
                        message="Claim references unverified evidence",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True
            if application_track_id not in module.track_ids:
                errors.append(
                    ValidationIssue(
                        code="cross_track_evidence",
                        message="Claim references evidence outside the application track",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True

        if provenance.approved_claim_id is not None:
            if not _matches_approved_claim(
                provenance.approved_claim_id,
                claim.text,
                referenced_modules,
            ):
                errors.append(
                    ValidationIssue(
                        code="unapproved_wording",
                        message="Claim text does not match approved wording",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True

        if claim.kind in _EXACT_FACT_KINDS and referenced_facts:
            if not _matches_fact_text(claim.text, referenced_facts):
                errors.append(
                    ValidationIssue(
                        code="fact_text_mismatch",
                        message="Structured claim differs from verified fact",
                        claim_id=claim.claim_id,
                    )
                )
                claim_has_error = True

        numeric_tokens = _NUMBER_RE.findall(claim.text)
        if numeric_tokens and not _numbers_supported(numeric_tokens, referenced_facts):
            errors.append(
                ValidationIssue(
                    code="unsupported_metric",
                    message="Numeric claim is not supported by referenced facts",
                    claim_id=claim.claim_id,
                )
            )
            claim_has_error = True

        if not claim_has_error:
            validated_claim_ids.append(claim.claim_id)

    known_claim_ids = {claim.claim_id for claim in document.claims}
    for entry in document.entries:
        for claim_id in entry.claim_ids:
            if claim_id not in known_claim_ids:
                errors.append(
                    ValidationIssue(
                        code="missing_claim",
                        message="CV entry references missing claim",
                        claim_id=claim_id,
                    )
                )

    return ValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        validated_claim_ids=validated_claim_ids,
    )


def _matches_fact_text(text: str, facts: list[MasterFact]) -> bool:
    target = _normalize(text)
    for fact in facts:
        candidates = {fact.value, *fact.display_values.values()}
        if any(_normalize(candidate) == target for candidate in candidates):
            return True
    return False


def _matches_approved_claim(
    approved_claim_id: str,
    text: str,
    modules: list,
) -> bool:
    target = _normalize(text)
    for module in modules:
        for approved in module.claims:
            if approved.id != approved_claim_id:
                continue
            return any(
                _normalize(candidate) == target
                for candidate in approved.text_by_language.values()
            )
    return False


def _numbers_supported(tokens: list[str], facts: list[MasterFact]) -> bool:
    available: set[str] = set()
    for fact in facts:
        available.update(_NUMBER_RE.findall(fact.value))
        for display in fact.display_values.values():
            available.update(_NUMBER_RE.findall(display))
    return all(token in available for token in tokens)
