from pathlib import Path

import pytest

from app.cv.recruiter_policy import RecruiterPolicy, load_recruiter_policy


def _policy_payload() -> dict:
    return {
        "version": "recruiter-policy-v1",
        "max_projects": 4,
        "max_experience_entries": 5,
        "max_experience_bullets": 1,
        "max_skill_groups": 4,
        "max_skill_tokens": 24,
        "max_profile_claims": 3,
        "max_education_items": 4,
        "skill_groups": {},
    }


def test_default_policy_has_composition_caps_without_render_constraints() -> None:
    policy = load_recruiter_policy("config/recruiter_policy.yaml")

    assert policy.max_projects == 4
    assert policy.max_experience_entries == 5
    assert policy.max_experience_bullets == 1
    assert policy.max_skill_groups == 4
    assert policy.max_skill_tokens == 24
    assert policy.max_profile_claims == 3
    assert policy.max_education_items == 4
    assert policy.skill_groups["software_data"].labels["en"] == "Software & Data"
    assert not hasattr(policy, "max_pages")
    assert not hasattr(policy, "min_body_font_pt")
    assert not hasattr(policy, "preferred_body_font_pt")


def test_policy_rejects_unsupported_version() -> None:
    payload = _policy_payload()
    payload["version"] = "recruiter-policy-v999"

    with pytest.raises(ValueError, match="unsupported recruiter policy version"):
        RecruiterPolicy.model_validate(payload)


def test_policy_rejects_physical_render_fields() -> None:
    payload = _policy_payload()
    payload["max_pages"] = 1

    with pytest.raises(ValueError):
        RecruiterPolicy.model_validate(payload)


def test_policy_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(
        """
version: recruiter-policy-v1
max_projects: 4
max_experience_entries: 5
max_experience_bullets: 1
max_skill_groups: 4
max_skill_tokens: 24
max_profile_claims: 3
max_education_items: 4
skill_groups: {}
secret_override: true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_recruiter_policy(path)
