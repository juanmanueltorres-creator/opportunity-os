from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contributions.models import ProofOfWork

NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)


def make_proof(**overrides) -> ProofOfWork:
    payload = {
        "proof_id": "proof-1",
        "entry_id": "entry-1",
        "repository_full_name": "example/project",
        "artifact_ref": "github:pr:example/project#42",
        "artifact_url": "https://github.com/example/project/pull/42",
        "status": "OPEN",
        "observed_at": NOW,
        "evidence_refs": ["github:pr:example/project#42"],
    }
    payload.update(overrides)
    return ProofOfWork(**payload)


def test_merged_pr_is_public_proof_without_employment_semantics() -> None:
    proof = make_proof(status="MERGED")
    dumped = proof.model_dump()
    assert proof.status == "MERGED"
    assert "employment_interest" not in dumped
    assert "job_opening" not in dumped
    assert "hiring" not in dumped


def test_closed_unmerged_remains_distinct_from_merged() -> None:
    proof = make_proof(status="CLOSED_UNMERGED")
    assert proof.status == "CLOSED_UNMERGED"


def test_proof_requires_public_provenance() -> None:
    with pytest.raises(ValidationError):
        make_proof(evidence_refs=[])


def test_proof_rejects_naive_observed_at() -> None:
    with pytest.raises(ValidationError):
        make_proof(observed_at=datetime(2026, 9, 4, 3, 30))
