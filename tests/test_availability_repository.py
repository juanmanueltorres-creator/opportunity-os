from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.availability.repository import SQLiteAvailabilityRepository


NOW = datetime(2026, 9, 18, 18, 0, tzinfo=timezone.utc)


def _repository(tmp_path) -> SQLiteAvailabilityRepository:
    repository = SQLiteAvailabilityRepository(tmp_path / "opportunities.db")
    repository.initialize()
    return repository


def test_seen_observations_build_first_and_last_seen_projection(tmp_path) -> None:
    repository = _repository(tmp_path)

    repository.record_seen(
        "opp-1",
        observed_at=NOW - timedelta(days=2),
        evidence_source="workana",
        source_url="https://workana.com/job/1",
    )
    repository.record_seen(
        "opp-1",
        observed_at=NOW,
        evidence_source="workana",
        source_url="https://workana.com/job/1",
    )

    state = repository.get("opp-1")

    assert state is not None
    assert state.first_seen_at == NOW - timedelta(days=2)
    assert state.last_seen_at == NOW
    assert state.last_verified_at is None
    assert state.verification_source is None
    assert state.availability_state == "UNVERIFIED"
    assert state.observation_count == 2


def test_verified_open_updates_verification_memory(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.record_seen(
        "opp-1",
        observed_at=NOW - timedelta(days=1),
        evidence_source="getonboard",
    )
    repository.record_verification(
        "opp-1",
        is_open=True,
        observed_at=NOW,
        evidence_source="official_company_page",
        source_url="https://company.example/jobs/1",
        note="Open application form visible",
    )

    state = repository.get("opp-1")

    assert state is not None
    assert state.availability_state == "VERIFIED_OPEN"
    assert state.last_seen_at == NOW
    assert state.last_verified_at == NOW
    assert state.verification_source == "official_company_page"


def test_verified_closed_is_not_overridden_by_later_plain_seen_observation(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.record_verification(
        "opp-1",
        is_open=False,
        observed_at=NOW - timedelta(hours=2),
        evidence_source="official_company_page",
    )
    repository.record_seen(
        "opp-1",
        observed_at=NOW,
        evidence_source="aggregator",
    )

    state = repository.get("opp-1")

    assert state is not None
    assert state.availability_state == "VERIFIED_CLOSED"
    assert state.last_verified_at == NOW - timedelta(hours=2)
    assert state.last_seen_at == NOW


def test_later_verified_open_can_reverse_prior_verified_closed_state(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.record_verification(
        "opp-1",
        is_open=False,
        observed_at=NOW - timedelta(days=1),
        evidence_source="official_company_page",
    )
    repository.record_verification(
        "opp-1",
        is_open=True,
        observed_at=NOW,
        evidence_source="official_company_page",
    )

    state = repository.get("opp-1")

    assert state is not None
    assert state.availability_state == "VERIFIED_OPEN"
    assert state.last_verified_at == NOW


def test_absence_creates_no_observation_and_cannot_infer_closed(tmp_path) -> None:
    repository = _repository(tmp_path)

    assert repository.get("missing") is None
    assert repository.list_observations("missing") == []


def test_observation_history_is_append_only_and_ordered(tmp_path) -> None:
    repository = _repository(tmp_path)

    repository.record_seen(
        "opp-1",
        observed_at=NOW - timedelta(hours=3),
        evidence_source="source-a",
    )
    repository.record_verification(
        "opp-1",
        is_open=True,
        observed_at=NOW - timedelta(hours=2),
        evidence_source="official",
    )
    repository.record_seen(
        "opp-1",
        observed_at=NOW - timedelta(hours=1),
        evidence_source="source-a",
    )

    observations = repository.list_observations("opp-1")

    assert [item.observation_type for item in observations] == [
        "SEEN",
        "VERIFIED_OPEN",
        "SEEN",
    ]
    assert [item.observed_at for item in observations] == sorted(
        item.observed_at for item in observations
    )


def test_repository_persists_across_instances(tmp_path) -> None:
    path = tmp_path / "opportunities.db"
    first = SQLiteAvailabilityRepository(path)
    first.initialize()
    first.record_seen(
        "opp-1",
        observed_at=NOW,
        evidence_source="workana",
    )

    second = SQLiteAvailabilityRepository(path)
    second.initialize()

    state = second.get("opp-1")
    assert state is not None
    assert state.last_seen_at == NOW
