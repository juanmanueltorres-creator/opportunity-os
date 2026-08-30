import json
from pathlib import Path

import pytest

from app.cv.models import CVDocumentModel
from app.cv.recruiter_models import RecruiterDocumentModel


@pytest.mark.parametrize(
    "fixture_name",
    ["recruiter_software", "recruiter_tech_operations"],
)
def test_golden_projects_are_canonical_and_described(fixture_name: str) -> None:
    payload = json.loads(
        (Path("tests/fixtures") / f"{fixture_name}.json").read_text(encoding="utf-8")
    )
    recruiter = RecruiterDocumentModel.model_validate(payload["recruiter_document"])
    source = CVDocumentModel.model_validate(payload["source_document"])
    claims = {claim.claim_id: claim for claim in source.claims}

    assert recruiter.project_entries
    assert [entry.primary_claim_id for entry in recruiter.project_entries] == (
        recruiter.selected_project_claim_ids
    )

    for entry in recruiter.project_entries:
        assert len(entry.bullet_claim_ids) == 1

        primary = claims[entry.primary_claim_id]
        bullet = claims[entry.bullet_claim_ids[0]]
        assert primary.kind == "project"
        assert bullet.kind == "bullet"

        primary_fact_ids = set(source.provenance_map[primary.claim_id].fact_ids)
        bullet_fact_ids = set(source.provenance_map[bullet.claim_id].fact_ids)
        assert primary_fact_ids & bullet_fact_ids
