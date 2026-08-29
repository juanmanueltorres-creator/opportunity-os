from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.targets.models import (
    TargetAccount,
    TargetAccountAssessment,
    TargetAccountBatch,
    TargetAccountPolicy,
    TargetSignal,
)


def sourced_signal(label: str = "signal", value: float = 80) -> TargetSignal:
    return TargetSignal(
        label=label,
        value=value,
        source_url="https://example.com/source",
        observed_at=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
    )


def test_target_account_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TargetAccount(
            id="example",
            name="Example Corp",
            sectors=["technology"],
            role_families=[],
            capability_tags=[],
            proximity_bucket="REMOTE",
            scale_stability_signal=sourced_signal(),
            innovation_signal=sourced_signal(),
            contactability="GENERAL_CV",
            hiring_signal=sourced_signal(),
            unknown_private_field="nope",
        )


def test_scoring_signal_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        TargetSignal(label="ai adoption", value=90, observed_at=datetime(2026, 8, 28, 15, tzinfo=timezone.utc))


def test_scoring_signal_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        TargetSignal(
            label="ai adoption",
            value=90,
            source_note="public company report",
            observed_at=datetime(2026, 8, 28, 15),
        )


def test_target_account_requires_sourced_numeric_signals() -> None:
    account = TargetAccount(
        id="example",
        name="Example Corp",
        website="https://example.com",
        sectors=["technology"],
        role_families=["software"],
        capability_tags=["python"],
        proximity_bucket="REMOTE",
        scale_stability_signal=sourced_signal("scale", 75),
        innovation_signal=sourced_signal("innovation", 85),
        contactability="GENERAL_CV",
        hiring_signal=sourced_signal("hiring", 50),
        application_channel="https://example.com/careers",
    )
    assert account.innovation_signal.value == 85
    assert account.proximity_bucket == "REMOTE"


def test_assessment_exposes_components_and_action_state() -> None:
    assessment = TargetAccountAssessment(
        account_id="example",
        account_name="Example Corp",
        best_track_id="tech",
        capability_sector_fit=90,
        proximity_fit=100,
        scale_stability=75,
        innovation=85,
        contactability_fit=85,
        hiring_signal=50,
        account_affinity=84.8,
        confidence=90,
        reasons=["strong capability overlap"],
        risks=[],
        cooldown_active=False,
        recommended_action="PREPARE_SPECULATIVE",
    )
    assert assessment.account_affinity == 84.8
    assert assessment.recommended_action == "PREPARE_SPECULATIVE"


def test_target_policy_defaults_are_explicit() -> None:
    policy = TargetAccountPolicy()
    assert policy.cooldown_days == 30
    assert policy.max_items == 20
    assert policy.minimum_affinity == 65
    assert policy.minimum_confidence == 60


def test_batch_requires_timezone_aware_generated_at() -> None:
    with pytest.raises(ValidationError):
        TargetAccountBatch(
            policy=TargetAccountPolicy(),
            profile_fingerprint="abc123",
            generated_at=datetime(2026, 8, 28, 15),
            items=[],
        )
