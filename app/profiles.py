from pathlib import Path

import yaml
from pydantic import ValidationError

from app.models.domain import CandidateProfile


def load_profile(path: str | Path) -> CandidateProfile:
    profile_path = Path(path)

    try:
        with profile_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid candidate profile: {profile_path}") from exc

    try:
        return CandidateProfile.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid candidate profile: {profile_path}") from exc
