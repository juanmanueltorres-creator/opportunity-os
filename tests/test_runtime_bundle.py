from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.runtime_bundle import (
    build_runtime_manifest,
    validate_bundle_source_paths,
    write_sha256sums,
)


def _fake_typst(root: Path) -> None:
    binary = root / "bin" / "typst"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\necho 'typst 0.13.1'\n", encoding="utf-8")
    binary.chmod(0o755)


def test_runtime_manifest_is_sha_bound_and_records_renderer_runtime(tmp_path: Path) -> None:
    _fake_typst(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")

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
    assert manifest["rendercv_version"]
    assert manifest["typst_version"].startswith("typst ")
    assert manifest["pymupdf_version"]
    assert len(manifest["typst_sha256"]) == 64
    assert len(manifest["source_sha256"]) == 64
    assert manifest["built_at"] == "2026-08-30T23:00:00Z"


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
            Path("scripts/render_recruiter_previews.py"),
            Path("pyproject.toml"),
        ]
    )


def test_sha256sums_are_stable_and_exclude_the_checksum_file(tmp_path: Path) -> None:
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "a.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "typst").write_text("binary\n", encoding="utf-8")
    output = tmp_path / "SHA256SUMS"

    write_sha256sums(tmp_path, output)
    first = output.read_text(encoding="utf-8")
    write_sha256sums(tmp_path, output)
    second = output.read_text(encoding="utf-8")

    assert first == second
    assert "source/a.txt" in first
    assert "bin/typst" in first
    assert "SHA256SUMS" not in first


def test_manifest_is_json_serializable(tmp_path: Path) -> None:
    _fake_typst(tmp_path)
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "marker.txt").write_text("source", encoding="utf-8")
    manifest = build_runtime_manifest(
        root=tmp_path,
        git_sha="b" * 40,
        built_at="2026-08-30T23:00:00Z",
    )
    json.dumps(manifest, sort_keys=True)
