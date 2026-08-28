from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from app.connectors.base import ConnectorError
from app.models.domain import CandidateProfile, Opportunity
from app.radar.confidence import score_confidence
from app.radar.eligibility import evaluate_eligibility
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.models import EligibilityResult, RadarAssessment, SourceDiagnostic
from app.radar.profile import effective_tracks
from app.radar.ranking import RadarPolicy, rank_assessment
from app.radar.scoring import best_track_assessments
from app.radar.selector import ApplicationHistory, RadarRunMetadata, select_daily_batch
from app.radar.sources import ConfiguredConnector, ManualOpportunityInput
from app.radar.taxonomy import TaxonomyResolver
from app.repositories.enrichments import SQLiteEnrichmentRepository
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest


class RadarSourceError(Exception):
    """Public-safe failure when no candidate can be produced from failed sources."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: list[SourceDiagnostic] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = list(diagnostics or [])


class EmptyApplicationHistory:
    def was_applied(self, opportunity: Opportunity) -> bool:
        return False

    def last_company_role_contact_at(
        self,
        company: str,
        title: str,
    ) -> datetime | None:
        return None


class RadarService:
    def __init__(
        self,
        *,
        opportunity_repository: SQLiteOpportunityRepository,
        enrichment_repository: SQLiteEnrichmentRepository,
        connectors: list[ConfiguredConnector],
        extractor: RuleBasedRequirementExtractor,
        resolver: TaxonomyResolver,
        policy: RadarPolicy | None = None,
        history: ApplicationHistory | None = None,
        scoring_version: str = "v0.2a1",
    ) -> None:
        if not scoring_version.strip():
            raise ValueError("scoring_version must not be empty")
        self.opportunity_repository = opportunity_repository
        self.enrichment_repository = enrichment_repository
        self.connectors = list(connectors)
        self.extractor = extractor
        self.resolver = resolver
        self.policy = policy or RadarPolicy()
        self.history = history or EmptyApplicationHistory()
        self.scoring_version = scoring_version.strip()

    async def run(
        self,
        profile: CandidateProfile,
        *,
        now: datetime,
    ):
        run_at = _aware_utc(now)
        diagnostics = await self._ingest_sources()

        candidates = self.opportunity_repository.list_radar_candidates(
            now=run_at,
            lookback_days=self.policy.candidate_lookback_days,
        )
        failed_sources = sum(item.status == "error" for item in diagnostics)
        if (
            not candidates
            and self.connectors
            and failed_sources == len(self.connectors)
        ):
            raise RadarSourceError(
                "No radar candidates available",
                diagnostics=diagnostics,
            )

        taxonomy_versions = _taxonomy_versions(self.resolver)
        alias_registry_version = self.resolver.alias_registry.version
        version_tuple = (
            self.extractor.extractor_version,
            alias_registry_version,
            taxonomy_versions,
        )

        ranked_items: list[RadarAssessment] = []
        for opportunity in candidates:
            enrichment = self.enrichment_repository.get_current(
                opportunity.id,
                version_tuple,
            )
            if enrichment is None:
                enrichment = self.extractor.extract(opportunity).model_copy(
                    update={
                        "taxonomy_versions": dict(taxonomy_versions),
                        "created_at": run_at,
                    }
                )
                self.enrichment_repository.save(
                    enrichment,
                    extractor_version=self.extractor.extractor_version,
                    alias_registry_version=alias_registry_version,
                    taxonomy_versions=taxonomy_versions,
                )

            career, income = best_track_assessments(
                opportunity,
                enrichment,
                profile,
                self.resolver,
                now=run_at,
            )
            eligibility = _aggregate_eligibility(
                opportunity,
                enrichment,
                profile,
            )
            confidence = score_confidence(enrichment, career, income)
            ranked_items.append(
                rank_assessment(
                    opportunity,
                    enrichment,
                    eligibility,
                    career,
                    income,
                    confidence,
                    policy=self.policy,
                    scoring_version=self.scoring_version,
                    alias_registry_version=alias_registry_version,
                )
            )

        metadata = RadarRunMetadata(
            profile_fingerprint=_profile_fingerprint(profile),
            scoring_version=self.scoring_version,
            extractor_version=self.extractor.extractor_version,
            alias_registry_version=alias_registry_version,
            taxonomy_versions=taxonomy_versions,
            source_diagnostics=tuple(diagnostics),
        )
        return select_daily_batch(
            ranked_items,
            self.policy,
            self.history,
            now=run_at,
            metadata=metadata,
        )

    def import_manual(
        self,
        manual: ManualOpportunityInput,
        *,
        now: datetime,
    ) -> Opportunity:
        opportunity = manual.to_opportunity(_aware_utc(now))
        stored, _ = self.opportunity_repository.upsert(opportunity)
        return stored

    async def _ingest_sources(self) -> list[SourceDiagnostic]:
        diagnostics: list[SourceDiagnostic] = []
        for configured in self.connectors:
            try:
                result = await ingest(
                    configured.connector,
                    self.opportunity_repository,
                )
            except ConnectorError:
                diagnostics.append(
                    SourceDiagnostic(
                        source=configured.name,
                        status="error",
                        code="source_unavailable",
                        message="Source unavailable",
                    )
                )
                continue

            diagnostics.append(
                SourceDiagnostic(
                    source=configured.name,
                    status="ok",
                    code="source_ok",
                    message=(
                        f"Source processed: {result.created} created, "
                        f"{result.existing} existing"
                    ),
                )
            )
        return diagnostics


def _aggregate_eligibility(
    opportunity: Opportunity,
    enrichment,
    profile: CandidateProfile,
) -> EligibilityResult:
    results = [
        evaluate_eligibility(opportunity, enrichment, profile, track)
        for track in effective_tracks(profile)
    ]
    if not results:
        return EligibilityResult(eligible=True)

    eligible_results = [result for result in results if result.eligible]
    if eligible_results:
        return EligibilityResult(
            eligible=True,
            soft_risks=_dedupe(
                risk
                for result in eligible_results
                for risk in result.soft_risks
            ),
            unknowns=_dedupe(
                unknown
                for result in eligible_results
                for unknown in result.unknowns
            ),
        )

    return EligibilityResult(
        eligible=False,
        hard_fail_reasons=_dedupe(
            reason
            for result in results
            for reason in result.hard_fail_reasons
        ),
        soft_risks=_dedupe(
            risk
            for result in results
            for risk in result.soft_risks
        ),
        unknowns=_dedupe(
            unknown
            for result in results
            for unknown in result.unknowns
        ),
    )


def _profile_fingerprint(profile: CandidateProfile) -> str:
    canonical = json.dumps(
        profile.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _taxonomy_versions(resolver: TaxonomyResolver) -> dict[str, str]:
    snapshot = resolver.taxonomy_snapshot
    if snapshot is None:
        return {}
    return {"local": snapshot.version}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _dedupe(values) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
