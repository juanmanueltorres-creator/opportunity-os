from __future__ import annotations

from app.cv.models import CVDocumentModel, ValidationIssue
from app.cv.narrative.models import NarrativeQAResult
from app.cv.recruiter_models import RecruiterDocumentModel
from app.cv.strategy.models import CVStrategy, CoreMessage
from app.cv.strategy.policy import NarrativePolicy


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _claim_by_id(document: CVDocumentModel) -> dict[str, object]:
    return {claim.claim_id: claim for claim in document.claims}


def _visible_claim_ids(recruiter: RecruiterDocumentModel) -> set[str]:
    return set(recruiter.all_claim_ids())


def _strategy_fact_ids(strategy: CVStrategy) -> set[str]:
    return (
        set(strategy.must_show_fact_ids)
        | set(strategy.supporting_fact_ids)
        | set(strategy.optional_fact_ids)
    )


def _strategy_evidence_ids(strategy: CVStrategy) -> set[str]:
    return {
        evidence_id
        for message in strategy.core_messages
        for evidence_id in message.evidence_ids
    }


def _provenance_supports_refs(
    *,
    document: CVDocumentModel,
    claim_id: str,
    fact_ids: set[str],
    evidence_ids: set[str],
) -> bool:
    provenance = document.provenance_map.get(claim_id)
    if provenance is None:
        return False
    if set(provenance.fact_ids) & fact_ids:
        return True
    return bool(set(provenance.evidence_ids) & evidence_ids)


def _claim_supports_strategy(
    *,
    document: CVDocumentModel,
    claim_id: str,
    strategy: CVStrategy,
) -> bool:
    return _provenance_supports_refs(
        document=document,
        claim_id=claim_id,
        fact_ids=_strategy_fact_ids(strategy),
        evidence_ids=_strategy_evidence_ids(strategy),
    )


def _core_message_coverage(
    *,
    recruiter: RecruiterDocumentModel,
    document: CVDocumentModel,
    strategy: CVStrategy,
) -> dict[str, float]:
    visible_ids = _visible_claim_ids(recruiter)
    visible_fact_ids = {
        fact_id
        for claim_id in visible_ids
        for fact_id in document.provenance_map.get(claim_id, ()).fact_ids
    }
    coverage: dict[str, float] = {}
    for message in strategy.core_messages:
        message_facts = set(message.fact_ids)
        coverage[message.id] = len(message_facts & visible_fact_ids) / len(message_facts)
    return coverage


def _editorial_claim_ids(recruiter: RecruiterDocumentModel) -> list[str]:
    ordered: list[str] = []

    def add(claim_id: str) -> None:
        if claim_id and claim_id not in ordered:
            ordered.append(claim_id)

    for claim_id in recruiter.profile_claim_ids:
        add(claim_id)
    for group in recruiter.technology_groups:
        for claim_id in group.skill_claim_ids:
            add(claim_id)
    if recruiter.project_entries:
        for entry in recruiter.project_entries:
            add(entry.primary_claim_id)
            for claim_id in entry.bullet_claim_ids:
                add(claim_id)
    else:
        for claim_id in recruiter.selected_project_claim_ids:
            add(claim_id)
    for entry in recruiter.experience_entries:
        for claim_id in entry.bullet_claim_ids:
            add(claim_id)
    return ordered


def _scan_claim_ids(
    recruiter: RecruiterDocumentModel,
    *,
    max_claims: int,
) -> list[str]:
    ordered: list[str] = []

    def add(claim_id: str) -> None:
        if claim_id and claim_id not in ordered:
            ordered.append(claim_id)

    add(recruiter.headline_claim_id)
    for claim_id in recruiter.profile_claim_ids:
        add(claim_id)
    for group in recruiter.technology_groups:
        if group.skill_claim_ids:
            add(group.skill_claim_ids[0])
    for entry in recruiter.experience_entries:
        add(entry.primary_claim_id)
        if entry.bullet_claim_ids:
            add(entry.bullet_claim_ids[0])
    if recruiter.project_entries:
        for entry in recruiter.project_entries:
            add(entry.primary_claim_id)
            if entry.bullet_claim_ids:
                add(entry.bullet_claim_ids[0])
    else:
        for claim_id in recruiter.selected_project_claim_ids:
            add(claim_id)
    return ordered[:max_claims]


def _scanability_score(
    *,
    recruiter: RecruiterDocumentModel,
    document: CVDocumentModel,
    strategy: CVStrategy,
    max_claims: int,
) -> float:
    if not strategy.core_messages:
        return 1.0
    scan_ids = _scan_claim_ids(recruiter, max_claims=max_claims)
    recovered = 0
    for message in strategy.core_messages:
        if any(
            _provenance_supports_refs(
                document=document,
                claim_id=claim_id,
                fact_ids=set(message.fact_ids),
                evidence_ids=set(message.evidence_ids),
            )
            for claim_id in scan_ids
        ):
            recovered += 1
    return round(recovered / len(strategy.core_messages), 2)


def _positioning_message(strategy: CVStrategy) -> CoreMessage | None:
    for message in strategy.core_messages:
        if message.id == "positioning":
            return message
    for message in strategy.core_messages:
        if _normalize(message.message) == _normalize(strategy.positioning):
            return message
    return None


def _issue(code: str, message: str, claim_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, claim_id=claim_id)


class NarrativeQualityQA:
    def evaluate(
        self,
        *,
        recruiter_document: RecruiterDocumentModel,
        source_document: CVDocumentModel,
        strategy: CVStrategy,
        policy: NarrativePolicy,
    ) -> NarrativeQAResult:
        claim_by_id = _claim_by_id(source_document)
        coverage = _core_message_coverage(
            recruiter=recruiter_document,
            document=source_document,
            strategy=strategy,
        )
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        for message_id, value in coverage.items():
            if value == 0.0:
                errors.append(
                    _issue(
                        "narrative_core_message_uncovered",
                        "A core narrative message has no visible supporting provenance.",
                    )
                )

        editorial_ids = _editorial_claim_ids(recruiter_document)
        off_strategy_ids = [
            claim_id
            for claim_id in editorial_ids
            if not _claim_supports_strategy(
                document=source_document,
                claim_id=claim_id,
                strategy=strategy,
            )
        ]
        off_strategy_ratio = (
            len(off_strategy_ids) / len(editorial_ids) if editorial_ids else 0.0
        )
        if off_strategy_ratio > policy.max_off_strategy_claim_ratio:
            errors.append(
                _issue(
                    "narrative_off_strategy_ratio_exceeded",
                    "Visible editorial content exceeds the allowed off-strategy ratio.",
                )
            )

        competing_identity_ids = [
            claim_id
            for claim_id in recruiter_document.profile_claim_ids
            if claim_id in off_strategy_ids
        ]
        if len(competing_identity_ids) > policy.max_competing_identity_signals:
            errors.append(
                _issue(
                    "narrative_competing_identity_limit_exceeded",
                    "Top-of-document profile content exceeds the competing identity limit.",
                )
            )

        headline = claim_by_id.get(recruiter_document.headline_claim_id)
        if headline is not None:
            if _normalize(headline.text) != _normalize(strategy.positioning):
                errors.append(
                    _issue(
                        "narrative_positioning_mismatch",
                        "The recruiter headline does not match the approved strategy positioning.",
                        recruiter_document.headline_claim_id,
                    )
                )
            positioning_message = _positioning_message(strategy)
            if positioning_message is None or not _provenance_supports_refs(
                document=source_document,
                claim_id=recruiter_document.headline_claim_id,
                fact_ids=set(positioning_message.fact_ids) if positioning_message else set(),
                evidence_ids=set(positioning_message.evidence_ids) if positioning_message else set(),
            ):
                errors.append(
                    _issue(
                        "narrative_positioning_unsupported",
                        "The recruiter headline lacks positioning-message provenance.",
                        recruiter_document.headline_claim_id,
                    )
                )

        phrases = policy.generic_language_phrases.get(source_document.language, [])
        normalized_phrases = [_normalize(phrase) for phrase in phrases]
        for claim_id in editorial_ids:
            claim = claim_by_id.get(claim_id)
            if claim is None:
                continue
            normalized_text = _normalize(claim.text)
            if any(phrase and phrase in normalized_text for phrase in normalized_phrases):
                warnings.append(
                    _issue(
                        "narrative_generic_claim_detected",
                        "A visible editorial claim contains configured generic recruiting language.",
                        claim_id,
                    )
                )

        scanability_score = _scanability_score(
            recruiter=recruiter_document,
            document=source_document,
            strategy=strategy,
            max_claims=policy.max_scan_claims,
        )
        if scanability_score < policy.min_scanability_score:
            errors.append(
                _issue(
                    "narrative_scanability_below_threshold",
                    "The fast-scan view does not recover enough core narrative messages.",
                )
            )

        return NarrativeQAResult(
            valid=not errors,
            core_message_coverage=coverage,
            off_strategy_claim_ratio=off_strategy_ratio,
            competing_identity_count=len(competing_identity_ids),
            scanability_score=scanability_score,
            errors=errors,
            warnings=warnings,
        )
