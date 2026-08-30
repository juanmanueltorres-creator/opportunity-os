from app.cv.recruiter_policy import load_recruiter_policy


def test_default_recruiter_policy_requires_half_page_text_utilization() -> None:
    policy = load_recruiter_policy("config/recruiter_policy.yaml")

    assert policy.min_text_height_ratio == 0.50
