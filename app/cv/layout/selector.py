from __future__ import annotations

from collections.abc import Mapping

from app.cv.layout.models import LayoutProfile
from app.cv.strategy.models import CVStrategy


def select_layout_profile(
    *,
    strategy: CVStrategy,
    profiles: Mapping[str, LayoutProfile],
    track_layout_map: Mapping[str, str] | None = None,
) -> LayoutProfile:
    if strategy.preferred_layout_profile_id is not None:
        profile_id = strategy.preferred_layout_profile_id
    else:
        mapping = track_layout_map or {}
        profile_id = mapping.get(strategy.application_track_id, "compact_ats")

    try:
        return profiles[profile_id]
    except KeyError as exc:
        raise ValueError("layout_profile_unavailable") from exc
