from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.runtime_bundle import (
    build_runtime_manifest,
    copy_runtime_source,
    find_runtime_wheel,
    validate_bundle_source_paths,
    write_sha256sums,
)


def _fake_runtime_root(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    source.mkdir(parents=True)
    (source / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir()
    project_wheel = wheelhouse / "opportunity_os-0.2.0rc1-py3-none-any.whl"
    project_wheel.write_bytes(b"project-wheel")
    (wheelhouse / "rendercv-2.8-py3-none-any.whl").write_bytes(b"rendercv-wheel")
    (wheelhouse / "pymupdf-1.28.2-cp310-abi3-manylinux_2_28_x86_64.whl").write_bytes(
        b"pymupdf-wheel"
    )
    typst_wheel = wheelhouse / "typst-0.15.0-cp38-abi3-manylinux_2_17_x86_64.whl"
    typst_wheel.write_bytes(b"typst-wheel")
    return project_wheel, typst_wheel


def test_runtime_manifest_is_sha_bound_and_records_renderer_runtime(tmp_path: Path) -> None:
    project_wheel, typst_wheel = _fake_runtime_root(tmp_path)

    manifest = build_runtime_manifest(
        root=tmp_path,
        git_sha="a" * 40,
        built_at="2026-08-30T23:00:00Z",
    )

    assert manifest["schema_version"] == "offline-runtime-v1"
    assert manifest["git_sha"] == "a" * 40
    assert manifest["python"] == "3.12"
    assert manifest["platform"] == "linux-x86_64"
    assert manifest["renderer_version"] == "rendercv-typst-v1"
    assert manifest["opportunity_os_version"] == "0.2.0rc1"
    assert manifest["rendercv_version"] == "2.8"
    assert manifest["typst_version"] == "0.15.0"
    assert manifest["pymupdf_version"] == "1.28.2"
    assert manifest["project_wheel"] == project_wheel.name
    assert manifest["typst_wheel"] == typst_wheel.name
    assert manifest["project_wheel_sha256"] == hashlib.sha256(b"project-wheel").hexdigest()
    assert manifest["typst_wheel_sha256"] == hashlib.sha256(b"typst-wheel").hexdigest()
    assert len(manifest["source_sha256"]) == 64
    assert manifest["built_at"] == "2026-08-30T23:00:00Z"


def test_find_runtime_wheel_requires_exactly_one_matching_wheel(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    expected = wheelhouse / "typst-0.15.0-cp38-abi3-manylinux_2_17_x86_64.whl"
    expected.write_bytes(b"wheel")

    assert find_runtime_wheel(wheelhouse, "typst-") == expected

    (wheelhouse / "typst-0.15.1-cp38-abi3-manylinux_2_17_x86_64.whl").write_bytes(b"other")
    with pytest.raises(ValueError, match="exactly one"):
        find_runtime_wheel(wheelhouse, "typst-")


def test_copy_runtime_source_uses_public_allowlist_and_fictional_fixtures(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    destination = tmp_path / "bundle" / "source"
    for directory in ("app", "config", "data", "scripts", "tests/fixtures"):
        (repository / directory).mkdir(parents=True, exist_ok=True)
    (repository / "app" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository / "config" / "policy.yaml").write_text("version: 1\n", encoding="utf-8")
    (repository / "data" / "skill_aliases.yaml").write_text("aliases: {}\n", encoding="utf-8")
    (repository / "scripts" / "verify_offline_runtime.py").write_text("print('ok')\n", encoding="utf-8")
    (repository / "scripts" / "build_offline_runtime.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repository / "tests" / "fixtures" / "recruiter_software.json").write_text("{}\n", encoding="utf-8")
    (repository / "tests" / "fixtures" / "recruiter_tech_operations.json").write_text("{}\n", encoding="utf-8")
    (repository / "tests" / "fixtures" / "unrelated.json").write_text("{}\n", encoding="utf-8")
    (repository / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (repository / ".env").write_text("SECRET=bad\n", encoding="utf-8")
    (repository / "candidate.pdf").write_bytes(b"bad")

    copied = copy_runtime_source(repository_root=repository, destination=destination)
    relative = {path.relative_to(destination).as_posix() for path in copied}

    assert "app/module.py" in relative
    assert "config/policy.yaml" in relative
    assert "data/skill_aliases.yaml" in relative
    assert "scripts/verify_offline_runtime.py" in relative
    assert "scripts/build_offline_runtime.sh" in relative
    assert "tests/fixtures/recruiter_software.json" in relative
    assert "tests/fixtures/recruiter_tech_operations.json" in relative
    assert "tests/fixtures/unrelated.json" not in relative
    assert "pyproject.toml" in relative
    assert ".env" not in relative
    assert "candidate.pdf" not in relative


def test_runtime_source_privacy_guard_rejects_private_or_generated_paths() -> None:
    forbidden = [
        Path(".env"),
        Path("profile/master_facts.local.yaml"),
        Path("profile/evidence_catalog.local.yaml"),
        Path("profile/anything.local.yaml"),
        Path("state/outreach.local.sqlite3"),
        Path("artifacts/applications/app-1/cv.pdf"),
        Path("candidate.pdf"),
        Path("candidate.docx"),
    ]

    for path in forbidden:
        with pytest.raises(ValueError, match="forbidden runtime bundle path"):
            validate_bundle_source_paths([path])


def test_runtime_source_privacy_guard_allows_canonical_runtime_source() -> None:
    validate_bundle_source_paths(
        [
            Path("app/cv/recruiter_qa.py"),
            Path("config/rendercv_one_page.yaml"),
            Path("data/skill_aliases.yaml"),
            Path("scripts/render_recruiter_previews.py"),
            Path("tests/fixtures/recruiter_software.json"),
            Path("pyproject.toml"),
        ]
    )


def test_sha256sums_are_stable_and_exclude_the_checksum_file(tmp_path: Path) -> None:
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "a.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "wheelhouse").mkdir()
    (tmp_path / "wheelhouse" / "typst.whl").write_text("binary\n", encoding="utf-8")
    output = tmp_path / "SHA256SUMS"

    write_sha256sums(tmp_path, output)
    first = output.read_text(encoding="utf-8")
    write_sha256sums(tmp_path, output)
    second = output.read_text(encoding="utf-8")

    assert first == second
    assert "source/a.txt" in first
    assert "wheelhouse/typst.whl" in first
    assert "SHA256SUMS" not in first


def test_manifest_is_json_serializable(tmp_path: Path) -> None:
    _fake_runtime_root(tmp_path)
    manifest = build_runtime_manifest(
        root=tmp_path,
        git_sha="b" * 40,
        built_at="2026-08-30T23:00:00Z",
    )
    json.dumps(manifest, sort_keys=True)


def test_offline_bootstrap_is_checksum_sha_and_no_index_bound() -> None:
    text = Path("scripts/bootstrap_offline_runtime.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "sha256sum -c" in text
    assert "runtime_manifest.json" in text
    assert "EXPECTED_SHA" in text
    assert "PIP_NO_INDEX=1" in text
    assert "PIP_DISABLE_PIP_VERSION_CHECK=1" in text
    assert "--no-index" in text
    assert "--find-links" in text
    assert "PYTHONPATH" in text


def test_offline_verifier_checks_canonical_render_a4_text_and_links() -> None:
    text = Path("scripts/verify_offline_runtime.py").read_text(encoding="utf-8")

    assert "render_previews" in text
    assert "pymupdf" in text
    assert "page_count" in text
    assert "595" in text
    assert "842" in text
    assert "get_text" in text
    assert "get_links" in text
    assert "mailto:" in text
    assert "https://" in text
