from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.models.domain import Opportunity
from app.outreach.models import (
    ContactCandidate,
    ContactPolicy,
    ContactResolution,
    ContactResolutionResult,
)
from app.outreach.repository import SQLiteOutreachRepository
from app.radar.models import OpportunityEnrichment

_ACTIONABLE_EMAIL_STATUSES = {
    "VERIFIED_DIRECT",
    "VERIFIED_OFFICIAL",
    "VERIFIED_ENRICHED",
}


class ContactResolutionService:
    def __init__(
        self,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def resolve(
        self,
        *,
        opportunity: Opportunity,
        enrichment: OpportunityEnrichment,
        candidates: list[ContactCandidate],
        policy: ContactPolicy,
        ledger: SQLiteOutreachRepository,
        now: datetime,
    ) -> ContactResolutionResult:
        now_utc = _require_aware(now)

        if ledger.has_successful_send_for_opportunity(opportunity.id):
            return ContactResolutionResult(
                status="BLOCKED_POLICY",
                candidates=candidates,
                errors=["already_sent"],
            )

        if any(candidate.opportunity_id != opportunity.id for candidate in candidates):
            return ContactResolutionResult(
                status="BLOCKED_POLICY",
                candidates=candidates,
                errors=["candidate_opportunity_mismatch"],
            )

        all_candidates = [
            *self._published_candidates(opportunity, enrichment),
            *candidates,
        ]
        priority_index = {
            channel: index for index, channel in enumerate(policy.priority)
        }
        ranked = sorted(
            all_candidates,
            key=lambda candidate: (
                priority_index.get(candidate.channel, len(priority_index)),
                -candidate.confidence,
                candidate.candidate_id,
            ),
        )

        recruiter_cap_hit = False
        for candidate in ranked:
            if candidate.channel == "MANUAL_FORM":
                return ContactResolutionResult(
                    status="MANUAL_ONLY",
                    resolution=self._resolution_from_candidate(
                        candidate,
                        policy=policy,
                        now=now_utc,
                    ),
                    candidates=ranked,
                )

            if candidate.channel == "VERIFIED_RECRUITER":
                recruiter_count = ledger.count_recruiter_contacts_for_company_day(
                    opportunity.company,
                    now_utc.date(),
                )
                if recruiter_count >= policy.max_recruiter_contacts_per_company_day:
                    recruiter_cap_hit = True
                    continue

                if candidate.email is None:
                    if (
                        candidate.requires_paid_enrichment
                        and candidate.verification_status
                        == "IDENTITY_VERIFIED_EMAIL_UNKNOWN"
                    ):
                        return ContactResolutionResult(
                            status="REQUIRES_ENRICHMENT",
                            candidates=ranked,
                            errors=["paid_enrichment_required"],
                        )
                    continue

            if candidate.email is None:
                continue
            if candidate.verification_status not in _ACTIONABLE_EMAIL_STATUSES:
                continue

            return ContactResolutionResult(
                status="RESOLVED",
                resolution=self._resolution_from_candidate(
                    candidate,
                    policy=policy,
                    now=now_utc,
                ),
                candidates=ranked,
            )

        if recruiter_cap_hit:
            return ContactResolutionResult(
                status="BLOCKED_POLICY",
                candidates=ranked,
                errors=["recruiter_daily_cap"],
            )

        return ContactResolutionResult(
            status="BLOCKED_NO_CONTACT",
            candidates=ranked,
            errors=["contact_unavailable"],
        )

    def _published_candidates(
        self,
        opportunity: Opportunity,
        enrichment: OpportunityEnrichment,
    ) -> list[ContactCandidate]:
        candidates: list[ContactCandidate] = []
        for hint in enrichment.application_contact_hints:
            if hint.kind != "PUBLISHED_EMAIL":
                continue
            candidates.append(
                ContactCandidate(
                    candidate_id=self.id_factory(),
                    opportunity_id=opportunity.id,
                    channel="PUBLISHED_VACANCY_EMAIL",
                    email=hint.value.casefold().strip(),
                    organization=opportunity.company,
                    source_kind="VACANCY",
                    source_ref=hint.source_url or opportunity.source_url,
                    confidence=hint.confidence,
                    verification_status="VERIFIED_DIRECT",
                    requires_paid_enrichment=False,
                    discovered_at=hint.discovered_at,
                )
            )
        return candidates

    def _resolution_from_candidate(
        self,
        candidate: ContactCandidate,
        *,
        policy: ContactPolicy,
        now: datetime,
    ) -> ContactResolution:
        now_utc = _require_aware(now)
        if candidate.channel == "MANUAL_FORM":
            reason = "manual route selected after email channels were unavailable"
        elif candidate.channel == "PUBLISHED_VACANCY_EMAIL":
            reason = "published vacancy email selected by contact priority"
        elif candidate.channel == "OFFICIAL_HR_EMAIL":
            reason = "official HR email selected by contact priority"
        else:
            reason = "verified recruiter selected by contact priority"

        return ContactResolution(
            opportunity_id=candidate.opportunity_id,
            selected_candidate_id=candidate.candidate_id,
            channel=candidate.channel,
            email=(candidate.email.casefold().strip() if candidate.email else None),
            contact_name=candidate.contact_name,
            contact_role=candidate.contact_role,
            organization=candidate.organization,
            source_kind=candidate.source_kind,
            source_ref=candidate.source_ref,
            confidence=candidate.confidence,
            verification_status=candidate.verification_status,
            resolution_reason=reason,
            resolved_at=now_utc,
            resolver_version=policy.resolver_version,
        )


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)
