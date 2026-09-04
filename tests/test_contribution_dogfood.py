import json
from pathlib import Path

from app.contributions.models import (
    ContributionEvent,
    ProofOfWork,
    PublicContributionEntry,
)
from app.contributions.projector import ContributionProjector

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "contributions" / "public_contribution_dogfood.json"
EXPECTED_CASE_IDS = {
    "hypothesized-geospatial-sdk",
    "open-unassigned-explicit-bug",
    "strong-issue-claimed-other",
    "moracarta-self-claimed-open-pr",
    "sunat-draft-pr-external-blocker",
}


def test_public_contribution_dogfood_projects_expected_contexts() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["version"] == "public-contribution-dogfood-v1"
    assert {case["case_id"] for case in payload["cases"]} == EXPECTED_CASE_IDS

    projector = ContributionProjector()
    for case in payload["cases"]:
        entry = PublicContributionEntry.model_validate(case["entry"])
        events = [
            ContributionEvent.model_validate(event)
            for event in case["events"]
        ]
        context = projector.project(entry=entry, events=events)
        expected = case["expected"]
        assert context.stage == expected["stage"], case["case_id"]
        assert (
            context.task_claim_state == expected["task_claim_state"]
        ), case["case_id"]
        assert context.blocking_reason == expected["blocking_reason"], case["case_id"]
        if case["proof"] is not None:
            proof = ProofOfWork.model_validate(case["proof"])
            assert proof.status == expected["proof_status"], case["case_id"]


def test_public_contribution_fixture_contains_no_private_mail_material() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    lower = raw.lower()
    assert "@gmail.com" not in lower
    assert "@mi.unc.edu.ar" not in lower
    assert '"email_body"' not in lower
    assert '"provider_payload"' not in lower
    assert '"raw_mime"' not in lower
    assert '"private_note"' not in lower
