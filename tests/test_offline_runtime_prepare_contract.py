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


def test_offline_verifier_enforces_language_decision_contract() -> None:
    text = Path("scripts/verify_offline_runtime.py").read_text(encoding="utf-8")

    assert 'result.get("language")' in text
    assert 'result.get("language_basis")' in text
    assert 'packet.get("language_decision")' in text
    assert 'packet.get("cv_document")' in text
    assert "offline application language mismatch" in text


def test_recruiter_renderer_uses_non_deprecated_pymupdf_import() -> None:
    text = Path("app/cv/renderers/rendercv_typst.py").read_text(encoding="utf-8")

    assert "import pymupdf as fitz" in text
    assert "\nimport fitz\n" not in text
