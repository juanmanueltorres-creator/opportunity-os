from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, model_validator

from app.cv.models import StrictCVModel

ATS_ROUNDTRIP_POLICY_VERSION = "ats-roundtrip-policy-v1"


class ATSRecoveryThresholds(StrictCVModel):
    identity: float = Field(ge=0, le=1)
    contact: float = Field(ge=0, le=1)
    experience: float = Field(ge=0, le=1)
    skills: float = Field(ge=0, le=1)
    education: float = Field(ge=0, le=1)
    links: float = Field(ge=0, le=1)


class ATSRoundTripPolicy(StrictCVModel):
    version: str = Field(min_length=1)
    thresholds: ATSRecoveryThresholds

    @model_validator(mode="after")
    def validate_contract(self) -> "ATSRoundTripPolicy":
        if self.version != ATS_ROUNDTRIP_POLICY_VERSION:
            raise ValueError(f"unsupported ATS round-trip policy version: {self.version}")
        if self.thresholds.identity != 1.0:
            raise ValueError("identity recovery threshold must be 1.0")
        return self


def load_ats_roundtrip_policy(path: str | Path) -> ATSRoundTripPolicy:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ATS round-trip policy root must be a mapping")
    return ATSRoundTripPolicy.model_validate(payload)
