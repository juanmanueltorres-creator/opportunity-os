from pathlib import Path

import pytest
import yaml

from app.cv.strategy.policy import NarrativePolicy, load_narrative_policy


def _payload() -> dict:
    return {
        "version": "narrative-policy-v1",
        "max_core_messages": 3,
        "positioning_message_importance": 10.0,
        "default_section_order": [
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
            "languages",
            "links",
        ],
        "requirement_importance_weights": {
            "mandatory": 3.0,
            "preferred": 2.0,
            "unknown": 1.0,
        },
        "support_level_weights": {
            "EXACT_VERIFIED": 3.0,
            "APPROVED_ALIAS": 2.5,
            "TAXONOMY_RELATED": 1.0,
            "UNKNOWN": 0.0,
        },
        "priority_requirement_bonus": 1.0,
    }


def _qa_payload() -> dict:
    payload = _payload()
    payload.update(
        {
            "max_off_strategy_claim_ratio": 0.35,
            "max_competing_identity_signals": 1,
            "min_scanability_score": 0.67,
            "generic_language_phrases": {
                "en": ["results-driven", "passionate"],
                "es": ["orientado a resultados", "apasionado"],
            },
        }
    )
    return payload


def test_narrative_policy_loads_default_contract(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(_payload(), sort_keys=False), encoding="utf-8")

    policy = load_narrative_policy(path)

    assert policy.version == "narrative-policy-v1"
    assert policy.max_core_messages == 3
    assert policy.support_level_weights["EXACT_VERIFIED"] == 3.0


def test_narrative_policy_accepts_versioned_qa_thresholds() -> None:
    policy = NarrativePolicy.model_validate(_qa_payload())

    assert policy.max_off_strategy_claim_ratio == 0.35
    assert policy.max_competing_identity_signals == 1
    assert policy.min_scanability_score == 0.67
    assert set(policy.generic_language_phrases) == {"en", "es"}


def test_narrative_policy_rejects_out_of_range_off_strategy_ratio() -> None:
    payload = _qa_payload()
    payload["max_off_strategy_claim_ratio"] = 1.1

    with pytest.raises(ValueError):
        NarrativePolicy.model_validate(payload)


def test_narrative_policy_rejects_incomplete_generic_language_keys() -> None:
    payload = _qa_payload()
    payload["generic_language_phrases"] = {"en": ["passionate"]}

    with pytest.raises(ValueError, match="generic_language_phrases"):
        NarrativePolicy.model_validate(payload)


def test_narrative_policy_rejects_duplicate_generic_phrase() -> None:
    payload = _qa_payload()
    payload["generic_language_phrases"]["en"] = ["passionate", " PASSIONATE "]

    with pytest.raises(ValueError, match="generic_language_phrases"):
        NarrativePolicy.model_validate(payload)


def test_narrative_policy_rejects_missing_support_weight() -> None:
    payload = _payload()
    payload["support_level_weights"].pop("TAXONOMY_RELATED")

    with pytest.raises(ValueError, match="support_level_weights"):
        NarrativePolicy.model_validate(payload)


def test_narrative_policy_rejects_more_than_three_core_messages() -> None:
    payload = _payload()
    payload["max_core_messages"] = 4

    with pytest.raises(ValueError):
        NarrativePolicy.model_validate(payload)


def test_narrative_policy_rejects_unknown_fields() -> None:
    payload = _payload()
    payload["secret_override"] = True

    with pytest.raises(ValueError):
        NarrativePolicy.model_validate(payload)
