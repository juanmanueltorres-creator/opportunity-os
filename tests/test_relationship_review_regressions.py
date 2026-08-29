from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import CandidateProfile
from app.relationships.context import SQLiteRelationshipMemory
from app.relationships.models import (
    CareerContact,
    RelationshipAccount,
    RelationshipContext,
    RelationshipEvent,
    RelationshipPolicy,
)
from app.relationships.repository import SQLiteRelationshipRepository
from app.relationships.service import RelationshipService
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.targets.models import TargetAccount, TargetAccountBatch, TargetAccountPolicy, TargetSignal
from app.targets.service import TargetRadarService

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _signal(label: str, value: float) -> TargetSignal:
    return TargetSignal(
        label=label,
        value=value,
        source_note="public regression fixture",
        observed_at=NOW,
    )


def _target() -> TargetAccount:
    return TargetAccount(
        id="example-co",
        name="Example Co",
        sectors=["technology"],
        role_families=["software engineer"],
        capability_tags=["python"],
        proximity_bucket="REMOTE",
        scale_stability_signal=_signal("scale", 90),
        innovation_signal=_signal("innovation", 90),
        contactability="GENERAL_CV",
        hiring_signal=_signal("hiring", 80),
    )


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Candidate",
        skills=["python"],
        roles=["software engineer"],
        domains=["technology"],
    )


class ReasonAwareMemory:
    def __init__(self) -> None:
        self.seen_reason: str | None = None

    def account_ids(self) -> list[str]:
        return ["example-co"]

    def context_for(
        self,
        account_id: str,
        *,
        now: datetime,
        current_reason: str | None = None,
    ) -> RelationshipContext:
        self.seen_reason = current_reason
        action = "FOLLOW_UP" if current_reason == "new backend role" else "PREPARE_SPECULATIVE"
        return RelationshipContext(
            account_id=account_id,
            relationship_state="DORMANT",
            cooldown_active=False,
            open_process=False,
            usable_contact_count=1,
            held_contact_count=0,
            recommended_relationship_action=action,
            reason=current_reason or "no current reason",
            generated_at=now,
        )


def test_target_radar_service_forwards_account_current_reason() -> None:
    memory = ReasonAwareMemory()
    service = TargetRadarService(targets=[_target()], relationship_memory=memory)

    batch = service.run(
        _profile(),
        now=NOW,
        current_reasons={"example-co": "new backend role"},
    )

    assert memory.seen_reason == "new backend role"
    assert batch.items[0].recommended_action == "FOLLOW_UP"


class CapturingTargetService:
    def __init__(self) -> None:
        self.current_reasons: dict[str, str] | None = None

    def run(
        self,
        profile: CandidateProfile,
        *,
        now: datetime,
        current_reasons: dict[str, str] | None = None,
    ) -> TargetAccountBatch:
        self.current_reasons = current_reasons
        return TargetAccountBatch(
            policy=TargetAccountPolicy(),
            profile_fingerprint="profile",
            generated_at=now,
            items=[],
        )


def test_target_radar_api_forwards_explicit_current_reasons(tmp_path: Path) -> None:
    target_service = CapturingTargetService()
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "db.sqlite3"),
        profile=_profile(),
        enable_default_radar=False,
        target_service=target_service,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/targets/radar/run",
            json={"current_reasons": {"example-co": "new backend role"}},
        )

    assert response.status_code == 200
    assert target_service.current_reasons == {"example-co": "new backend role"}


def test_relationship_context_api_forwards_explicit_current_reason(tmp_path: Path) -> None:
    memory = ReasonAwareMemory()
    app = create_app(
        repository=SQLiteOpportunityRepository(tmp_path / "db.sqlite3"),
        profile=_profile(),
        enable_default_radar=False,
        enable_default_targets=False,
        relationship_memory=memory,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/relationships/example-co/context",
            params={"current_reason": "new backend role"},
        )

    assert response.status_code == 200
    assert memory.seen_reason == "new backend role"
    assert response.json()["recommended_relationship_action"] == "FOLLOW_UP"


def _relationship_repo(tmp_path: Path) -> SQLiteRelationshipRepository:
    repo = SQLiteRelationshipRepository(tmp_path / "relationships.sqlite3")
    repo.initialize()
    return repo


def _contact() -> CareerContact:
    return CareerContact(
        contact_id="contact-1",
        account_id="account-1",
        person="Private Person",
        role="Recruiter",
        contact_type="RECRUITER",
        verification_status="VERIFIED",
        observed_at=NOW,
        disposition="AVAILABLE",
        active=True,
    )


def test_recent_process_closed_is_not_immediately_derived_dormant(tmp_path: Path) -> None:
    repo = _relationship_repo(tmp_path)
    repo.save_contact(_contact())
    repo.save_account(
        RelationshipAccount(
            account_id="account-1",
            company="Example Co",
            relationship_state="PROCESS_CLOSED",
            open_process=False,
            updated_at=NOW - timedelta(days=1),
        )
    )
    memory = SQLiteRelationshipMemory(
        repo,
        RelationshipPolicy(follow_up_min_days=5),
    )

    context = memory.context_for("account-1", now=NOW)

    assert context.relationship_state == "PROCESS_CLOSED"
    assert context.recommended_relationship_action == "PREPARE_SPECULATIVE"


def test_out_of_order_relationship_event_is_rejected_without_regressing_projection(
    tmp_path: Path,
) -> None:
    repo = _relationship_repo(tmp_path)
    service = RelationshipService(repo)
    service.register_account(
        RelationshipAccount(
            account_id="account-1",
            company="Example Co",
            updated_at=NOW - timedelta(days=2),
        )
    )

    newer = RelationshipEvent(
        event_id="event-newer",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW,
        metadata={"official_channel": "careers-form"},
    )
    older = RelationshipEvent(
        event_id="event-older",
        account_id="account-1",
        kind="CONTACTED",
        occurred_at=NOW - timedelta(days=1),
        metadata={"official_channel": "careers-form"},
    )

    service.record(newer)
    with pytest.raises(ValueError, match="out-of-order"):
        service.record(older)

    stored = repo.get_account("account-1")
    assert stored is not None
    assert stored.last_contacted_at == NOW
    assert repo.get_event("event-older") is None
