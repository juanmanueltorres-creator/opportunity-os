from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest

from app.connectors.base import ConnectorError
from app.models.domain import CandidateProfile, CandidateTrack, Opportunity
from app.radar.extractor import RuleBasedRequirementExtractor
from app.radar.ranking import RadarPolicy
from app.radar.sources import ConfiguredConnector, ManualOpportunityInput
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver
from app.repositories.enrichments import SQLiteEnrichmentRepository
from app.repositories.opportunities import SQLiteOpportunityRepository

NOW = datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc)


class SuccessfulConnector:
    async def fetch(self) -> list[Opportunity]:
        return [_opportunity("greenhouse:ok-1", source="greenhouse")]


class FailingConnector:
    async def fetch(self) -> list[Opportunity]:
        raise ConnectorError("DO_NOT_ECHO_UPSTREAM_SECRET")


class EmptyHistory:
    def was_applied(self, opportunity: Opportunity) -> bool:
        return False

    def last_company_role_contact_at(self, company: str, title: str):
        return None


def _module():
    return import_module("app.radar.service")


def _opportunity(item_id: str, *, source: str = "greenhouse") -> Opportunity:
    source_id = item_id.split(":", 1)[-1]
    return Opportunity(
        id=item_id,
        source=source,
        source_id=source_id,
        source_url=f"https://example.com/jobs/{source_id}",
        company=f"Example {source_id}",
        title="Support Analyst",
        description="Must have Python.",
        discovered_at=NOW - timedelta(hours=2),
        location="Remote, Argentina",
        remote_policy="remote",
        published_at=NOW - timedelta(days=1),
    )


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Example Candidate",
        roles=["Support Analyst"],
        skills=["Python"],
        locations=["Argentina"],
        remote_preferences=["remote"],
        tracks=[
            CandidateTrack(
                id="income-support",
                label="Immediate income support",
                intents=["INCOME_NOW"],
                roles=["Support Analyst"],
                skills=["Python"],
                accepted_work_modes=["remote"],
            )
        ],
    )


def _resolver(tmp_path) -> TaxonomyResolver:
    alias_path = tmp_path / "aliases.yaml"
    alias_path.write_text("version: '1'\nentries: []\n", encoding="utf-8")
    return TaxonomyResolver(alias_registry=AliasRegistry.load(alias_path))


def _service(tmp_path, connectors: list[ConfiguredConnector]):
    opportunity_repository = SQLiteOpportunityRepository(tmp_path / "opportunities.db")
    opportunity_repository.initialize()
    enrichment_repository = SQLiteEnrichmentRepository(tmp_path / "opportunities.db")
    enrichment_repository.initialize()
    return _module().RadarService(
        opportunity_repository=opportunity_repository,
        enrichment_repository=enrichment_repository,
        connectors=connectors,
        extractor=RuleBasedRequirementExtractor(extractor_version="rules-v1"),
        resolver=_resolver(tmp_path),
        policy=RadarPolicy(),
        history=EmptyHistory(),
        scoring_version="v0.2a1",
    ), opportunity_repository, enrichment_repository


@pytest.mark.asyncio
async def test_one_source_failure_is_isolated_and_successful_opportunity_is_assessed(tmp_path) -> None:
    service, opportunities, enrichments = _service(
        tmp_path,
        [
            ConfiguredConnector(name="greenhouse:example", connector=SuccessfulConnector()),
            ConfiguredConnector(name="lever:broken", connector=FailingConnector()),
        ],
    )

    batch = await service.run(_profile(), now=NOW)

    assert opportunities.get("greenhouse:ok-1") is not None
    assert batch.count == 1
    assert batch.items[0].opportunity.id == "greenhouse:ok-1"
    assert batch.items[0].selected_intent == "INCOME_NOW"
    assert batch.items[0].tier == "HIGH"
    assert batch.profile_fingerprint.startswith("sha256:")

    failed = next(item for item in batch.source_diagnostics if item.source == "lever:broken")
    assert failed.status == "error"
    assert failed.code == "source_unavailable"
    assert failed.message == "Source unavailable"
    assert "DO_NOT_ECHO_UPSTREAM_SECRET" not in failed.model_dump_json()

    current = enrichments.get_current(
        "greenhouse:ok-1",
        ("rules-v1", "1", {}),
    )
    assert current is not None


@pytest.mark.asyncio
async def test_all_sources_fail_but_stored_candidate_still_runs(tmp_path) -> None:
    service, opportunities, _ = _service(
        tmp_path,
        [ConfiguredConnector(name="greenhouse:broken", connector=FailingConnector())],
    )
    opportunities.upsert(_opportunity("greenhouse:stored-1"))

    batch = await service.run(_profile(), now=NOW)

    assert batch.count == 1
    assert batch.items[0].opportunity.id == "greenhouse:stored-1"
    assert batch.source_diagnostics[0].status == "error"


@pytest.mark.asyncio
async def test_all_sources_fail_without_stored_candidates_raises_public_safe_error(tmp_path) -> None:
    service, _, _ = _service(
        tmp_path,
        [ConfiguredConnector(name="greenhouse:broken", connector=FailingConnector())],
    )

    with pytest.raises(_module().RadarSourceError) as excinfo:
        await service.run(_profile(), now=NOW)

    assert str(excinfo.value) == "No radar candidates available"
    assert "DO_NOT_ECHO_UPSTREAM_SECRET" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_manual_import_persists_and_enters_same_radar_pipeline(tmp_path) -> None:
    service, opportunities, _ = _service(tmp_path, [])
    manual = ManualOpportunityInput(
        source="community-board",
        source_url="https://example.com/jobs/manual-support",
        title="Support Analyst",
        company="Example Cooperative",
        raw_description="Must have Python.",
        location="Remote, Argentina",
        remote_policy="remote",
        published_at=NOW - timedelta(days=1),
    )

    stored = service.import_manual(manual, now=NOW)
    batch = await service.run(_profile(), now=NOW)

    assert opportunities.get(stored.id) == stored
    assert batch.count == 1
    assert batch.items[0].opportunity.id == stored.id
