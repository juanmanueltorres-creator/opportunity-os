from datetime import datetime, timezone

from app.models.domain import CandidateProfile
from app.targets.models import TargetAccount, TargetAccountPolicy, TargetSignal
from app.targets.service import TargetRadarService

NOW = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)


def signal(label: str, value: float) -> TargetSignal:
    return TargetSignal(
        label=label,
        value=value,
        source_note="public fixture",
        observed_at=NOW,
    )


def target(target_id: str, capability: str, innovation: float) -> TargetAccount:
    return TargetAccount(
        id=target_id,
        name=target_id.title(),
        sectors=["technology"],
        role_families=["software engineer"],
        capability_tags=[capability],
        proximity_bucket="REMOTE",
        scale_stability_signal=signal("scale", 80),
        innovation_signal=signal("innovation", innovation),
        contactability="GENERAL_CV",
        hiring_signal=signal("hiring", 50),
    )


def test_service_scores_registry_and_returns_deterministic_batch() -> None:
    service = TargetRadarService(
        targets=[
            target("python-co", "python", 90),
            target("java-co", "java", 60),
        ],
        policy=TargetAccountPolicy(),
    )
    profile = CandidateProfile(
        name="Candidate",
        skills=["python"],
        roles=["software engineer"],
        domains=["technology"],
    )
    first = service.run(profile, now=NOW)
    second = service.run(profile, now=NOW)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.items[0].account_id == "python-co"
    assert first.profile_fingerprint == second.profile_fingerprint
