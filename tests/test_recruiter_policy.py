from pathlib import Path

import pytest

from app.cv.recruiter_policy import RecruiterPolicy, load_recruiter_policy


def test_default_policy_is_exactly_one_page_and_has_fixed_caps(tmp_path: Path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        """
version: recruiter-policy-v1
max_pages: 1
min_body_font_pt: 9.0
preferred_body_font_pt: 9.4
max_projects: 4
max_experience_entries: 5
max_experience_bullets: 1
max_skill_groups: 4
max_skill_tokens: 24
max_profile_claims: 3
max_education_items: 4
skill_groups:
  software_data:
    en: Software & Data
    es: Software y Datos
    members: [Python, SQL]
  additional:
    en: Additional
    es: Adicional
    members: []
""".strip(),
        encoding="utf-8",
    )

    policy = load_recruiter_policy(path)

    assert policy.max_pages == 1
    assert policy.min_body_font_pt == 9.0
    assert policy.preferred_body_font_pt == 9.4
    assert policy.max_projects == 4
    assert policy.max_experience_entries == 5
    assert policy.max_experience_bullets == 1
    assert policy.max_skill_groups == 4
    assert policy.max_skill_tokens == 24
    assert policy.max_profile_claims == 3
    assert policy.max_education_items == 4
    assert policy.skill_groups["software_data"].labels["en"] == "Software & Data"


def test_policy_rejects_any_page_count_other_than_one():
    with pytest.raises(ValueError, match="max_pages must be exactly 1"):
        RecruiterPolicy(
            version="recruiter-policy-v1",
            max_pages=2,
            min_body_font_pt=9.0,
            preferred_body_font_pt=9.4,
            max_projects=4,
            max_experience_entries=5,
            max_experience_bullets=1,
            max_skill_groups=4,
            max_skill_tokens=24,
            max_profile_claims=3,
            max_education_items=4,
            skill_groups={},
        )


def test_policy_rejects_preferred_font_below_minimum():
    with pytest.raises(ValueError, match="preferred_body_font_pt"):
        RecruiterPolicy(
            version="recruiter-policy-v1",
            max_pages=1,
            min_body_font_pt=9.0,
            preferred_body_font_pt=8.9,
            max_projects=4,
            max_experience_entries=5,
            max_experience_bullets=1,
            max_skill_groups=4,
            max_skill_tokens=24,
            max_profile_claims=3,
            max_education_items=4,
            skill_groups={},
        )


def test_policy_rejects_unknown_fields(tmp_path: Path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        """
version: recruiter-policy-v1
max_pages: 1
min_body_font_pt: 9.0
preferred_body_font_pt: 9.4
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
