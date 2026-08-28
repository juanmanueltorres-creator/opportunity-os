from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.cv.hashing import canonical_sha256
from app.cv.models import MasterFact, PreparationResult, ValidationIssue

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def test_verified_fact_requires_verification_metadata() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-postgis",
            kind="skill",
            value="PostGIS",
            track_ids=["tech"],
            verified=True,
        )


def test_manual_confirmation_allows_self_attested_contact_without_source_ref() -> None:
    fact = MasterFact(
        id="contact-email",
        kind="contact",
        value="alex@example.test",
        track_ids=["tech", "hospitality"],
        verified=True,
        verification_method="manual_confirmation",
        verified_at=NOW,
    )

    assert fact.source_ref is None


def test_evidence_backed_fact_requires_source_ref() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="skill-python",
            kind="skill",
            value="Python",
            track_ids=["tech"],
            verified=True,
            verification_method="repository_evidence",
            verified_at=NOW,
        )


def test_verified_fact_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="contact-city",
            kind="location",
            value="Cordoba, Argentina",
            track_ids=["tech"],
            verified=True,
            verification_method="manual_confirmation",
            verified_at=datetime(2026, 8, 28, 12, 0),
        )


def test_cv_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MasterFact(
            id="contact-name",
            kind="identity",
            value="Alex Example",
            verified=False,
            invented_field="not allowed",
        )


def test_blocked_preparation_result_cannot_contain_packet() -> None:
    with pytest.raises(ValidationError):
        PreparationResult(
            status="BLOCKED_VALIDATION",
            packet={"status": "PREPARED"},
            errors=[
                ValidationIssue(
                    code="claim_validation_failed",
                    message="blocked",
                )
            ],
        )


def test_canonical_hash_ignores_mapping_key_order() -> None:
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_canonical_hash_preserves_visible_list_order() -> None:
    assert canonical_sha256({"bullets": ["A", "B"]}) != canonical_sha256(
        {"bullets": ["B", "A"]}
    )
