from app.cv.models import CVClaim
from app.cv.recruiter_composer import _group_skills
from app.cv.recruiter_policy import load_recruiter_policy


def test_group_skills_deduplicates_equal_visible_text_and_keeps_supported_claim() -> None:
    claims = [
        CVClaim(
            claim_id="fact:procurement",
            section="skills",
            kind="skill",
            text="Compras",
        ),
        CVClaim(
            claim_id="fact:purchasing",
            section="skills",
            kind="skill",
            text=" compras ",
        ),
    ]

    groups = _group_skills(
        claims=claims,
        policy=load_recruiter_policy("config/recruiter_policy.yaml"),
        supported_ids={"fact:purchasing"},
        source_order={"fact:procurement": 0, "fact:purchasing": 1},
    )

    selected = [
        claim_id
        for group in groups
        for claim_id in group.skill_claim_ids
    ]

    assert selected == ["fact:purchasing"]
