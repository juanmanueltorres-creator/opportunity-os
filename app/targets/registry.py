from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.targets.models import TargetAccount


class TargetRegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[TargetAccount]


def load_target_registry(path: str | Path) -> list[TargetAccount]:
    registry_path = Path(path)
    try:
        payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        document = TargetRegistryDocument.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid target registry: {registry_path}") from exc
    return document.targets
