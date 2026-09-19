from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.availability.models import AvailabilityObservation
from app.availability.repository import SQLiteAvailabilityRepository
from app.availability.verification_models import (
    VerificationConfirmRequest,
    VerificationEvidence,
)
from app.availability.verification_service import AvailabilityVerificationService
from app.models.domain import Opportunity
from app.repositories.opportunities import SQLiteOpportunityRepository


NOW = datetime(2026, 9, 18, 19, 0, tzinfo=timezone.utc)


def _repositories(tmp_path):
    path = tmp_path / "opportunities.db"
    opportunities = SQLiteOpportunityRepository(path)
    availability = SQLiteAvailabilityRepository(path)
    opportunities.initialize()
    availability.initialize()
    return opportunities, availability


def _service(tmp_path):
    opportunities, availability = _repositories(tmp_path)
    stored, _ = opportunities.upsert(
        Opportunity(
            id="opp-1",
            source="manual",
            source_id="opp-1",
            source_url="https://company.example/jobs/opp-1",
            company="Example Co",
            title="GIS Analyst",
            description="QGIS role",
            discovered_at=NOW - timedelta(days=1),
            published_at=NOW - timedelta(days=2),
            status="open",
        )
    )
    return (
        AvailabilityVerificationService(
            opportunity_repository=opportunities,
            availability_repository=availability,
        ),
        opportunities,
        availability,
        stored,
    )


def _evidence(
    *,
    decision: str = "OPEN",
    observed_at: datetime = NOW,
    source: str = "careers.example.com",
    url: str = "https://careers.example.com/jobs/opp-1",
) -> VerificationEvidence:
    return VerificationEvidence(
        opportunity_id="opp-1",
        decision=decision,
        observed_at=observed_at,
        evidence_kind="OFFICIAL_COMPANY_PAGE",
        evidence_source=source,
        source_url=url,
        note="Application page reviewed manually",
    )


def _request(
    evidence: VerificationEvidence,
    preview_sha256: str,
    *,
    confirmed_at: datetime = NOW,
) -> VerificationConfirmRequest:
    return VerificationConfirmRequest(
        evidence=evidence,
        preview_sha256=preview_sha256,
        confirmed_by="operator",
        confirmed_at=confirmed_at,
    )


def test_preview_is_read_only_and_ready(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    evidence = _evidence()

    preview = service.preview(evidence)

    assert preview.status == "READY"
    assert preview.current_state == "UNVERIFIED"
    assert preview.proposed_state == "VERIFIED_OPEN"
    assert preview.observation_count == 0
    assert preview.external_actions == []
    assert availability.list_observations("opp-1") == []


def test_preview_missing_opportunity_is_blocked_without_write(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    evidence = _evidence().model_copy(update={"opportunity_id": "missing"})

    preview = service.preview(evidence)

    assert preview.status == "BLOCKED"
    assert preview.errors == ["opportunity_not_found"]
    assert availability.list_observations("missing") == []


def test_confirm_exact_preview_records_verified_open_with_provenance(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    evidence = _evidence()
    preview = service.preview(evidence)

    result = service.confirm(
        _request(evidence, preview.preview_sha256),
        processed_at=NOW + timedelta(seconds=1),
    )

    assert result.status == "RECORDED"
    assert result.receipt is not None
    assert result.receipt.resulting_state == "VERIFIED_OPEN"
    state = availability.get("opp-1")
    assert state is not None
    assert state.availability_state == "VERIFIED_OPEN"
    observations = availability.list_observations("opp-1")
    assert len(observations) == 1
    observation = observations[0]
    assert observation.evidence_kind == "OFFICIAL_COMPANY_PAGE"
    assert observation.confirmed_by == "operator"
    assert observation.confirmed_at == NOW
    assert observation.preview_sha256 == preview.preview_sha256


def test_confirm_closed_records_explicit_closed_state_without_mutating_opportunity(tmp_path) -> None:
    service, opportunities, availability, stored = _service(tmp_path)
    evidence = _evidence(decision="CLOSED")
    preview = service.preview(evidence)

    result = service.confirm(
        _request(evidence, preview.preview_sha256),
        processed_at=NOW + timedelta(seconds=1),
    )

    assert result.status == "RECORDED"
    state = availability.get("opp-1")
    assert state is not None
    assert state.availability_state == "VERIFIED_CLOSED"
    assert opportunities.get(stored.id).status == "open"


def test_exact_retry_is_idempotent_and_preserves_original_confirmation(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    evidence = _evidence()
    preview = service.preview(evidence)
    request = _request(evidence, preview.preview_sha256)

    first = service.confirm(
        request,
        processed_at=NOW + timedelta(seconds=1),
    )
    second = service.confirm(
        request.model_copy(
            update={
                "confirmed_by": "another_operator",
                "confirmed_at": NOW + timedelta(minutes=1),
            }
        ),
        processed_at=NOW + timedelta(minutes=1),
    )

    assert first.status == "RECORDED"
    assert second.status == "ALREADY_RECORDED"
    assert first.receipt is not None
    assert second.receipt is not None
    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert second.receipt.confirmed_by == "operator"
    assert second.receipt.confirmed_at == NOW
    assert len(availability.list_observations("opp-1")) == 1


def test_concurrent_seen_observation_blocks_stale_preview(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    evidence = _evidence()
    preview = service.preview(evidence)
    availability.record_seen(
        "opp-1",
        observed_at=NOW + timedelta(seconds=1),
        evidence_source="aggregator",
        source_url="https://aggregator.example/jobs/1",
    )

    result = service.confirm(
        _request(
            evidence,
            preview.preview_sha256,
            confirmed_at=NOW + timedelta(seconds=2),
        ),
        processed_at=NOW + timedelta(seconds=2),
    )

    assert result.status == "BLOCKED_STALE_PREVIEW"
    assert result.errors == ["stale_preview"]
    assert [
        item.observation_type
        for item in availability.list_observations("opp-1")
    ] == ["SEEN"]


def test_preview_after_existing_same_workflow_evidence_is_already_verified(tmp_path) -> None:
    service, _, _, _ = _service(tmp_path)
    evidence = _evidence()
    first_preview = service.preview(evidence)
    first = service.confirm(
        _request(evidence, first_preview.preview_sha256),
        processed_at=NOW + timedelta(seconds=1),
    )
    assert first.status == "RECORDED"

    second_preview = service.preview(evidence)

    assert second_preview.status == "ALREADY_VERIFIED"


def test_same_prior_direct_verification_without_workflow_receipt_blocks_duplicate_workflow_import(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    evidence = _evidence()
    availability.record(
        AvailabilityObservation(
            opportunity_id="opp-1",
            observation_type="VERIFIED_OPEN",
            observed_at=evidence.observed_at,
            evidence_source=evidence.evidence_source,
            source_url=evidence.source_url,
            note=evidence.note,
            evidence_kind=evidence.evidence_kind,
        )
    )
    preview = service.preview(evidence)

    assert preview.status == "ALREADY_VERIFIED"
    result = service.confirm(
        _request(evidence, preview.preview_sha256),
        processed_at=NOW + timedelta(seconds=1),
    )
    assert result.status == "BLOCKED"
    assert result.errors == [
        "verification_already_exists_without_workflow_receipt"
    ]
    assert len(availability.list_observations("opp-1")) == 1


def test_confirmation_cannot_precede_observation() -> None:
    evidence = _evidence(observed_at=NOW)

    with pytest.raises(
        ValueError,
        match="confirmed_at must be at or after evidence observed_at",
    ):
        _request(
            evidence,
            "0" * 64,
            confirmed_at=NOW - timedelta(seconds=1),
        )


def test_invalid_evidence_url_fails_closed() -> None:
    with pytest.raises(ValueError, match="source_url must use http or https"):
        _evidence(url="file:///tmp/fake")


def test_old_availability_table_is_migrated_in_place(tmp_path) -> None:
    path = tmp_path / "opportunities.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE opportunity_availability_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL,
                observation_type TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                evidence_source TEXT NOT NULL,
                source_url TEXT,
                note TEXT
            )
            """
        )

    repository = SQLiteAvailabilityRepository(path)
    repository.initialize()

    with sqlite3.connect(path) as conn:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(opportunity_availability_observations)"
            ).fetchall()
        }
    assert {
        "evidence_kind",
        "confirmed_by",
        "confirmed_at",
        "preview_sha256",
    }.issubset(columns)


def test_future_confirmation_is_blocked_without_write(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    evidence = _evidence()
    preview = service.preview(evidence)

    result = service.confirm(
        _request(
            evidence,
            preview.preview_sha256,
            confirmed_at=NOW + timedelta(minutes=5),
        ),
        processed_at=NOW + timedelta(minutes=1),
    )

    assert result.status == "BLOCKED"
    assert result.errors == ["confirmation_in_future"]
    assert availability.list_observations("opp-1") == []


def test_older_confirmed_evidence_reports_persisted_projection(tmp_path) -> None:
    service, _, availability, _ = _service(tmp_path)
    availability.record_verification(
        "opp-1",
        is_open=False,
        observed_at=NOW + timedelta(minutes=10),
        evidence_source="official_company_page",
        source_url="https://careers.example.com/jobs/opp-1",
    )
    older_open = _evidence(
        decision="OPEN",
        observed_at=NOW,
        source="archived_official_page",
        url="https://careers.example.com/jobs/opp-1?snapshot=older",
    )
    preview = service.preview(older_open)
    assert preview.current_state == "VERIFIED_CLOSED"

    result = service.confirm(
        _request(
            older_open,
            preview.preview_sha256,
            confirmed_at=NOW + timedelta(minutes=20),
        ),
        processed_at=NOW + timedelta(minutes=20),
    )

    assert result.status == "RECORDED"
    assert result.receipt is not None
    assert result.receipt.decision == "OPEN"
    assert result.receipt.resulting_state == "VERIFIED_CLOSED"
    projected = availability.get("opp-1")
    assert projected is not None
    assert projected.availability_state == "VERIFIED_CLOSED"
    assert len(availability.list_observations("opp-1")) == 2
