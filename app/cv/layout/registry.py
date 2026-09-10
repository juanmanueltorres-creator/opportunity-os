from __future__ import annotations

from pathlib import Path

import yaml

from app.cv.layout.models import LayoutProfile

_REQUIRED_PROFILE_IDS = {"technical_clean", "operations_clean", "compact_ats"}


def load_layout_profiles(path: str | Path) -> dict[str, LayoutProfile]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("layout profile registry root must be a mapping")

    profiles: dict[str, LayoutProfile] = {}
    for key, value in payload.items():
        profile = LayoutProfile.model_validate(value)
        if key != profile.id:
            raise ValueError("layout profile registry key/id mismatch")
        profiles[profile.id] = profile

    if set(profiles) != _REQUIRED_PROFILE_IDS:
        raise ValueError("layout profile registry incomplete")
    return dict(sorted(profiles.items()))
