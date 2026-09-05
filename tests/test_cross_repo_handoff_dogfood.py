import json
from datetime import datetime
from pathlib import Path

from app.contributions.observations import ContributionPreview
from app.handoffs.models import QuestionResearchHandoff, ResearchOpportunityHandoff
from app.handoffs.preview import preview_research_opportunity_handoff
from app.handoffs.public_contribution_research import (
    build_public_contribution_candidate_handoff,
)


FIXTURES = Path("tests/fixtures/handoffs")
PUBLIC_QUESTION = FIXTURES / "question_research_public_github_v01.json"
PUBLIC_PREVIEW = FIXTURES / "contribution_preview_public_issue_v01.json"
PUBLIC_CANDIDATE = FIXTURES / "public_contribution_candidate_v01.json"
WATER_HANDOFF = FIXTURES / "research_opportunity_water_san_juan_v01.json"
GUIDE = Path("docs/CROSS_REPO_HANDOFF_V01.md")

FORBIDDEN_AUTHORITY_KEYS = {
    "job_opening",
    "employment_interest",
    "target_account",
    "buyer",
    "customer",
    "contact_permission",
    "send_authority",
    "apply_authority",
}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested in value.values():
            keys.update(_all_keys(nested))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for nested in value:
            keys.update(_all_keys(nested))
        return keys
    return set()


def test_public_github_chain_builds_expected_candidate_without_hiring_authority() -> None:
    question = QuestionResearchHandoff.model_validate(_load_json(PUBLIC_QUESTION))
    contribution_preview = ContributionPreview.model_validate(_load_json(PUBLIC_PREVIEW))
    expected = ResearchOpportunityHandoff.model_validate(_load_json(PUBLIC_CANDIDATE))

    built = build_public_contribution_candidate_handoff(
        question,
        contribution_preview,
        handoff_id=expected.handoff_id,
        created_at=expected.created_at,
    )

    assert built.model_dump(mode="json") == expected.model_dump(mode="json")
    assert built.candidate.kind == "PUBLIC_CONTRIBUTION_CANDIDATE"
    assert built.candidate.task_claim_state == "AVAILABLE"
    assert built.candidate.task_ref is not None
    assert built.source_freshness == "AS_OF_EXPORT"
    assert not (_all_keys(_load_json(PUBLIC_CANDIDATE)) & FORBIDDEN_AUTHORITY_KEYS)


def test_public_github_candidate_is_import_eligible_only_with_explicit_local_metadata() -> None:
    handoff = ResearchOpportunityHandoff.model_validate(_load_json(PUBLIC_CANDIDATE))
    preview = preview_research_opportunity_handoff(
        handoff,
        contribution_entry_id="entry:dogfood:public-issue:001",
        contribution_discovered_at=datetime.fromisoformat("2026-09-04T22:30:00-03:00"),
    )

    assert preview.status == "REVIEWABLE"
    assert preview.allowed_dispositions == [
        "IMPORT_PUBLIC_CONTRIBUTION",
        "WATCH",
        "DISCARD",
    ]
    assert preview.contribution_entry is not None
    assert preview.contribution_entry.task_claim_state == "AVAILABLE"
    assert preview.source_freshness == "AS_OF_EXPORT"


def test_water_actor_need_remains_research_without_manufacturing_actor_or_action() -> None:
    handoff_payload = _load_json(WATER_HANDOFF)
    handoff = ResearchOpportunityHandoff.model_validate(handoff_payload)
    preview = preview_research_opportunity_handoff(handoff)

    assert handoff.candidate.kind == "ACTOR_NEED_HYPOTHESIS"
    assert preview.source_freshness == "AS_OF_EXPORT"
    assert preview.research_status == "researching"
    assert preview.actor_refs == []
    assert preview.evidence_refs == handoff.candidate.evidence_refs
    assert preview.assumptions == handoff.candidate.assumptions
    assert preview.missing_context == handoff.candidate.missing_context
    assert preview.allowed_dispositions == ["WATCH", "DISCARD"]
    assert preview.contribution_entry is None
    assert not (_all_keys(handoff_payload) & FORBIDDEN_AUTHORITY_KEYS)


def test_dogfood_fixtures_are_sanitized_and_do_not_encode_private_job_search_state() -> None:
    joined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PUBLIC_QUESTION, PUBLIC_PREVIEW, PUBLIC_CANDIDATE, WATER_HANDOFF)
    ).lower()

    assert "@" not in joined
    assert "access_token" not in joined
    assert "gmail" not in joined
    assert "apollo" not in joined
    assert "juan.manuel" not in joined


def test_operator_guide_preserves_original_preview_as_only_import_continuation() -> None:
    guide = GUIDE.read_text(encoding="utf-8")

    assert "original existing ContributionPreview" in guide
    assert "explicit human confirmation" in guide
    assert "ephemeral contribution entry" in guide
    assert "never an import payload" in guide
    assert "research_opportunity_water_san_juan_v01.json" in guide
    assert "public_contribution_candidate_v01.json" in guide
