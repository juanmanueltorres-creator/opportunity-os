from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from app.cv.renderers.rendercv_typst import RENDERER_VERSION

_SCHEMA_VERSION = "offline-runtime-v1"
_TARGET_PYTHON = "3.12"
_TARGET_PLATFORM = "linux-x86_64"
_FORBIDDEN_EXACT = {
    ".env",
    "profile/master_facts.local.yaml",
    "profile/evidence_catalog.local.yaml",
    "state/outreach.local.sqlite3",
    "state/relationships.local.sqlite3",
}
_FORBIDDEN_SUFFIXES = (".local.yaml", ".pdf", ".docx")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        raise ValueError(f"runtime source path does not exist: {root}")
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _normalise(path: Path) -> str:
    return path.as_posix().lstrip("./")


def validate_bundle_source_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        value = _normalise(path)
        lower = value.casefold()
        if (
            value in _FORBIDDEN_EXACT
            or lower.endswith(_FORBIDDEN_SUFFIXES)
            or lower.endswith(".sqlite3")
            or lower.startswith("artifacts/applications/")
            or "/artifacts/applications/" in lower
        ):
            raise ValueError(f"forbidden runtime bundle path: {value}")


def build_runtime_manifest(*, root: Path, git_sha: str, built_at: str) -> dict[str, object]:
    if len(git_sha) != 40 or any(char not in "0123456789abcdefABCDEF" for char in git_sha):
        raise ValueError("git_sha must be a 40-character hexadecimal commit SHA")
    if f"{sys.version_info.major}.{sys.version_info.minor}" != _TARGET_PYTHON:
        raise ValueError(f"runtime bundle must be built with Python {_TARGET_PYTHON}")
    if platform.system().casefold() != "linux" or platform.machine().casefold() not in {
        "x86_64",
        "amd64",
    }:
        raise ValueError("runtime bundle must be built on Linux x86_64")

    typst_path = root / "bin" / "typst"
    if not typst_path.is_file():
        raise ValueError("runtime bundle is missing bin/typst")
    source_root = root / "source"
    typst_version = subprocess.check_output(
        [str(typst_path), "--version"],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()
    if not typst_version:
        raise ValueError("typst --version returned empty output")

    return {
        "schema_version": _SCHEMA_VERSION,
        "git_sha": git_sha.lower(),
        "python": _TARGET_PYTHON,
        "platform": _TARGET_PLATFORM,
        "rendercv_version": importlib.metadata.version("rendercv"),
        "typst_version": typst_version,
        "pymupdf_version": importlib.metadata.version("PyMuPDF"),
        "renderer_version": RENDERER_VERSION,
        "typst_sha256": _sha256_file(typst_path),
        "source_sha256": _sha256_tree(source_root),
        "built_at": built_at,
    }


def write_sha256sums(root: Path, output_path: Path) -> None:
    output = output_path.resolve()
    lines: list[str] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.resolve() == output:
            continue
        relative = path.relative_to(root).as_posix()
        lines.append(f"{_sha256_file(path)}  {relative}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
