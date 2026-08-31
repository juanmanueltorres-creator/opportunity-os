from __future__ import annotations

from pathlib import Path
import tomllib


def test_pypdf_is_a_production_dependency() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = data["project"]["dependencies"]
    dev_dependencies = data["project"]["optional-dependencies"]["dev"]

    assert any(dependency.startswith("pypdf>=5") for dependency in runtime_dependencies)
    assert not any(dependency.startswith("pypdf") for dependency in dev_dependencies)


def test_offline_verifier_executes_canonical_prepare_to_prepared_packet() -> None:
    text = Path("scripts/verify_offline_runtime.py").read_text(encoding="utf-8")

    assert "app.application.prepare" in text
    assert '"PREPARED"' in text or "'PREPARED'" in text
    assert "application_packet.json" in text
    assert "renderer_version" in text
