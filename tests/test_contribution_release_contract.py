from pathlib import Path

from app.contributions.models import (
    ContributionContext,
    ProofOfWork,
    PublicContributionEntry,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "PUBLIC_CONTRIBUTION_CORE_V1.md"


def test_contribution_models_have_no_employment_authority_fields() -> None:
    forbidden = {
        "employment_interest",
        "job_opening",
        "application_status",
        "send_authorized",
        "apply_authorized",
    }
    for model in (PublicContributionEntry, ContributionContext, ProofOfWork):
        assert forbidden.isdisjoint(model.model_fields)


def test_public_contribution_v1_does_not_wire_an_api_route() -> None:
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "app.contributions" not in main
    assert "/contributions" not in main
    assert "/contribution" not in main


def test_public_contract_states_the_epistemic_boundary() -> None:
    document = CONTRACT.read_text(encoding="utf-8")
    assert "PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING" in document
    assert "PR_OPENED != EMPLOYMENT_INTEREST" in document
    assert "PR_MERGED != EMPLOYMENT_INTEREST" in document


def test_public_contract_keeps_contribution_and_hiring_funnels_separate() -> None:
    document = CONTRACT.read_text(encoding="utf-8")
    assert "Public Contribution Core" in document
    assert "contribution funnel" in document.lower()
    assert "hiring funnel" in document.lower()
