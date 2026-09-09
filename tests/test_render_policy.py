import pytest

from app.cv.render_policy import RenderPolicy, load_render_policy


def test_default_render_policy_preserves_one_page_behavior() -> None:
    policy = load_render_policy("config/render_policy.yaml")

    assert policy.version == "render-policy-v1"
    assert policy.page_size == "A4"
    assert policy.preferred_pages == 1
    assert policy.max_pages == 1
    assert policy.min_body_font_pt == 9.0
    assert policy.preferred_body_font_pt == 9.4


def test_render_policy_can_explicitly_allow_two_pages() -> None:
    policy = RenderPolicy(
        version="render-policy-v1",
        page_size="A4",
        preferred_pages=1,
        max_pages=2,
        min_body_font_pt=9.0,
        preferred_body_font_pt=9.4,
    )

    assert policy.max_pages == 2


def test_render_policy_rejects_preferred_pages_above_max() -> None:
    with pytest.raises(ValueError, match="preferred_pages"):
        RenderPolicy(
            version="render-policy-v1",
            page_size="A4",
            preferred_pages=2,
            max_pages=1,
            min_body_font_pt=9.0,
            preferred_body_font_pt=9.4,
        )


def test_render_policy_rejects_preferred_font_below_minimum() -> None:
    with pytest.raises(ValueError, match="preferred_body_font_pt"):
        RenderPolicy(
            version="render-policy-v1",
            page_size="A4",
            preferred_pages=1,
            max_pages=1,
            min_body_font_pt=9.5,
            preferred_body_font_pt=9.4,
        )


def test_render_policy_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        RenderPolicy.model_validate(
            {
                "version": "render-policy-v1",
                "page_size": "A4",
                "preferred_pages": 1,
                "max_pages": 1,
                "min_body_font_pt": 9.0,
                "preferred_body_font_pt": 9.4,
                "legacy_one_page": True,
            }
        )
