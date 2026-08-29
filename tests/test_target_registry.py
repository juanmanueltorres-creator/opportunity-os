from pathlib import Path

import pytest

from app.targets.registry import load_target_registry


def test_load_target_registry_accepts_fictional_yaml(tmp_path: Path) -> None:
    path = tmp_path / "targets.yaml"
    path.write_text(
        """targets:\n  - id: example\n    name: Example Corp\n    sectors: [technology]\n    role_families: [software]\n    capability_tags: [python]\n    proximity_bucket: REMOTE\n    scale_stability_signal:\n      label: established company\n      value: 80\n      source_url: https://example.com/about\n      observed_at: 2026-08-28T15:00:00Z\n    innovation_signal:\n      label: public ai program\n      value: 90\n      source_url: https://example.com/ai\n      observed_at: 2026-08-28T15:00:00Z\n    contactability: GENERAL_CV\n    hiring_signal:\n      label: careers portal\n      value: 50\n      source_url: https://example.com/careers\n      observed_at: 2026-08-28T15:00:00Z\n""",
        encoding="utf-8",
    )
    targets = load_target_registry(path)
    assert [target.id for target in targets] == ["example"]


def test_invalid_registry_error_does_not_echo_private_contents(tmp_path: Path) -> None:
    path = tmp_path / "targets.local.yaml"
    path.write_text("targets: [private-secret-value", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_target_registry(path)
    assert "private-secret-value" not in str(exc.value)
    assert "Invalid target registry" in str(exc.value)


def test_unknown_target_field_is_rejected_safely(tmp_path: Path) -> None:
    path = tmp_path / "targets.yaml"
    path.write_text(
        """targets:\n  - id: example\n    name: Example Corp\n    sectors: []\n    role_families: []\n    capability_tags: []\n    proximity_bucket: UNKNOWN\n    scale_stability_signal: {label: scale, value: 50, source_note: public, observed_at: 2026-08-28T15:00:00Z}\n    innovation_signal: {label: innovation, value: 50, source_note: public, observed_at: 2026-08-28T15:00:00Z}\n    contactability: UNKNOWN\n    hiring_signal: {label: hiring, value: 50, source_note: public, observed_at: 2026-08-28T15:00:00Z}\n    private_email: secret@example.com\n""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        load_target_registry(path)
    assert "secret@example.com" not in str(exc.value)
