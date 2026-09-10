from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cv.layout.models import LayoutProfile
from app.cv.visual_policy import (
    VisualPolicy,
    density_thresholds_for_profile,
    load_visual_policy,
)


def _profile(profile_id: str, density: str) -> LayoutProfile:
    return LayoutProfile(
        version="layout-profile-v1",
        id=profile_id,
        design_path=f"config/layouts/{profile_id}.yaml",
        density=density,
        emphasis="neutral",
        ats_mode="strict",
    )


def _payload() -> dict:
    return {
        "version": "visual-policy-v1",
        "min_substantive_claims_for_underfill": 8,
        "underfill_warning_bottom_ratio": 0.45,
        "underfill_error_bottom_ratio": 0.30,
        "isolated_bottom_start_ratio": 0.88,
        "isolated_bottom_min_gap_pt": 72.0,
        "max_headline_lines": 2,
        "wall_text_warning_lines": 6,
        "wall_text_error_lines": 10,
        "wall_text_warning_chars": 420,
        "wall_text_error_chars": 700,
        "wall_text_max_list_marker_ratio": 0.50,
        "large_gap_warning_ratio": 0.12,
        "large_gap_error_ratio": 0.20,
        "density_warning_lines_per_page_inch": 5.0,
        "density_error_lines_per_page_inch": 6.2,
        "density_multipliers": {
            "comfortable": 0.92,
            "balanced": 1.00,
            "compact": 1.10,
        },
        "hierarchy_min_delta_pt": 1.0,
        "orphan_heading_bottom_ratio": 0.84,
        "orphan_heading_max_following_lines": 1,
    }


def test_default_visual_policy_loads_versioned_contract():
    policy = load_visual_policy(Path("config/visual_policy.yaml"))

    assert policy.version == "visual-policy-v1"
    assert policy.underfill_error_bottom_ratio < policy.underfill_warning_bottom_ratio
    assert policy.wall_text_warning_lines < policy.wall_text_error_lines
    assert policy.wall_text_warning_chars < policy.wall_text_error_chars
    assert policy.large_gap_warning_ratio < policy.large_gap_error_ratio
    assert (
        policy.density_warning_lines_per_page_inch
        < policy.density_error_lines_per_page_inch
    )
    assert set(policy.density_multipliers) == {
        "comfortable",
        "balanced",
        "compact",
    }


def test_visual_policy_rejects_unknown_fields():
    payload = _payload()
    payload["private_exception"] = True

    with pytest.raises(ValidationError):
        VisualPolicy.model_validate(payload)


def test_visual_policy_rejects_invalid_threshold_ordering():
    payload = _payload()
    payload["underfill_error_bottom_ratio"] = 0.60

    with pytest.raises(ValidationError):
        VisualPolicy.model_validate(payload)


def test_visual_policy_requires_exact_density_multiplier_keys():
    payload = _payload()
    payload["density_multipliers"] = {
        "comfortable": 0.92,
        "balanced": 1.0,
        "compact": 1.1,
        "special_private_track": 1.2,
    }

    with pytest.raises(ValidationError):
        VisualPolicy.model_validate(payload)


def test_profile_density_adjustment_is_deterministic_and_underfill_neutral():
    policy = VisualPolicy.model_validate(_payload())
    comfortable = _profile("technical_clean", "comfortable")
    balanced = _profile("operations_clean", "balanced")
    compact = _profile("compact_ats", "compact")

    comfortable_thresholds = density_thresholds_for_profile(policy, comfortable)
    balanced_thresholds = density_thresholds_for_profile(policy, balanced)
    compact_thresholds = density_thresholds_for_profile(policy, compact)

    assert comfortable_thresholds == density_thresholds_for_profile(
        policy, comfortable
    )
    assert comfortable_thresholds[0] < balanced_thresholds[0] < compact_thresholds[0]
    assert comfortable_thresholds[1] < balanced_thresholds[1] < compact_thresholds[1]
    assert policy.underfill_error_bottom_ratio == 0.30
    assert policy.underfill_warning_bottom_ratio == 0.45
