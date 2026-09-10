from __future__ import annotations

import importlib

import pytest
import yaml


def _policy_module():
    try:
        return importlib.import_module("app.cv.ats.policy")
    except ModuleNotFoundError as exc:
        if exc.name in {"app.cv.ats", "app.cv.ats.policy"}:
            pytest.fail("ATS round-trip policy is not implemented")
        raise


def _payload() -> dict:
    return {
        "version": "ats-roundtrip-policy-v1",
        "thresholds": {
            "identity": 1.0,
            "contact": 1.0,
            "experience": 1.0,
            "skills": 0.9,
            "education": 1.0,
            "links": 1.0,
        },
    }


def test_load_ats_roundtrip_policy_reads_versioned_thresholds(tmp_path) -> None:
    module = _policy_module()
    path = tmp_path / "ats.yaml"
    path.write_text(yaml.safe_dump(_payload()), encoding="utf-8")

    policy = module.load_ats_roundtrip_policy(path)

    assert policy.version == "ats-roundtrip-policy-v1"
    assert policy.thresholds.identity == 1.0
    assert policy.thresholds.skills == 0.9


def test_identity_threshold_must_be_full_recovery(tmp_path) -> None:
    module = _policy_module()
    payload = _payload()
    payload["thresholds"]["identity"] = 0.9
    path = tmp_path / "ats.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="identity"):
        module.load_ats_roundtrip_policy(path)
