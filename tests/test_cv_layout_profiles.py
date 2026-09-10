from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cv.layout import LayoutProfile, load_layout_profiles


def test_public_registry_loads_exact_v1_profiles() -> None:
    profiles = load_layout_profiles("config/layout_profiles.yaml")
    assert list(profiles) == ["compact_ats", "operations_clean", "technical_clean"]
    assert profiles["technical_clean"].density == "comfortable"
    assert profiles["operations_clean"].emphasis == "experience"
    assert profiles["compact_ats"].ats_mode == "strict"


def test_profile_rejects_narrative_and_render_fields() -> None:
    with pytest.raises(ValidationError):
        LayoutProfile.model_validate(
            {
                "version": "layout-profile-v1",
                "id": "technical_clean",
                "design_path": "config/layouts/technical_clean.yaml",
                "density": "comfortable",
                "emphasis": "technical",
                "ats_mode": "strict",
                "section_order": ["skills", "experience"],
                "max_pages": 2,
            }
        )


def test_profile_rejects_wrong_version_and_path_escape() -> None:
    with pytest.raises(ValidationError):
        LayoutProfile(
            version="layout-profile-v2",
            id="technical_clean",
            design_path="config/layouts/technical_clean.yaml",
            density="comfortable",
            emphasis="technical",
        )
    with pytest.raises(ValidationError):
        LayoutProfile(
            version="layout-profile-v1",
            id="technical_clean",
            design_path="../private.yaml",
            density="comfortable",
            emphasis="technical",
        )


def test_registry_rejects_key_id_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text(
        "technical_clean:\n"
        "  version: layout-profile-v1\n"
        "  id: compact_ats\n"
        "  design_path: config/layouts/compact_ats.yaml\n"
        "  density: compact\n"
        "  emphasis: neutral\n"
        "  ats_mode: strict\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="layout profile registry key/id mismatch"):
        load_layout_profiles(path)


def test_registry_requires_all_v1_profiles(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="layout profile registry incomplete"):
        load_layout_profiles(path)
