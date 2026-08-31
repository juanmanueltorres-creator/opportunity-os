from __future__ import annotations

import hashlib
import platform
import shutil
import sys
from pathlib import Path
from typing import Iterable

from app.cv.renderers.rendercv_typst import RENDERER_VERSION

_SCHEMA_VERSION = "offline-runtime-v1"
_SUPPORTED_PYTHON = {"3.12", "3.13"}
_TARGET_PLATFORM = "linux-x86_64"
_FIXTURE_NAMES = (
    "recruiter_software.json",
    "recruiter_tech_operations.json",
)
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
    value = path.as_posix()
    return value[2:] if value.startswith("./") else value


def runtime_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


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
            or "__pycache__" in lower.split("/")
        ):
            raise ValueError(f"forbidden runtime bundle path: {value}")


def find_runtime_wheel(wheelhouse: Path, prefix: str) -> Path:
    matches = sorted(
        path
        for path in wheelhouse.glob("*.whl")
        if path.name.casefold().startswith(prefix.casefold())
    )
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one runtime wheel with prefix {prefix!r}, found {len(matches)}"
        )
    return matches[0]


def _wheel_version(path: Path, prefix: str) -> str:
    name = path.name
    if not name.casefold().startswith(prefix.casefold()) or not name.endswith(".whl"):
        raise ValueError(f"unexpected wheel filename for {prefix!r}: {name}")
    remainder = name[len(prefix) :]
    version = remainder.split("-", 1)[0]
    if not version:
        raise ValueError(f"wheel filename has no version: {name}")
    return version


def _is_ephemeral_python_cache(path: Path) -> bool:
    return "__pycache__" in {part.casefold() for part in path.parts} or path.suffix.casefold() in {
        ".pyc",
        ".pyo",
    }


def copy_runtime_source(*, repository_root: Path, destination: Path) -> list[Path]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    copied: list[Path] = []
    for directory_name in ("app", "config", "data", "scripts"):
        source_dir = repository_root / directory_name
        if not source_dir.is_dir():
            continue
        for source in sorted(path for path in source_dir.rglob("*") if path.is_file()):
            relative = source.relative_to(repository_root)
            if _is_ephemeral_python_cache(relative):
                continue
            validate_bundle_source_paths([relative])
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target)

    pyproject = repository_root / "pyproject.toml"
    if not pyproject.is_file():
        raise ValueError("runtime source is missing pyproject.toml")
    validate_bundle_source_paths([Path("pyproject.toml")])
    target_pyproject = destination / "pyproject.toml"
    shutil.copy2(pyproject, target_pyproject)
    copied.append(target_pyproject)

    fixture_root = repository_root / "tests" / "fixtures"
    for fixture_name in _FIXTURE_NAMES:
        source = fixture_root / fixture_name
        if not source.is_file():
            raise ValueError(f"runtime source is missing fictional fixture {fixture_name}")
        relative = Path("tests") / "fixtures" / fixture_name
        validate_bundle_source_paths([relative])
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)

    return copied


def build_runtime_manifest(*, root: Path, git_sha: str, built_at: str) -> dict[str, object]:
    if len(git_sha) != 40 or any(char not in "0123456789abcdefABCDEF" for char in git_sha):
        raise ValueError("git_sha must be a 40-character hexadecimal commit SHA")
    python_version = runtime_python_version()
    if python_version not in _SUPPORTED_PYTHON:
        raise ValueError(
            "runtime bundle must be built with a supported Python version: "
            + ", ".join(sorted(_SUPPORTED_PYTHON))
        )
    if platform.system().casefold() != "linux" or platform.machine().casefold() not in {
        "x86_64",
        "amd64",
    }:
        raise ValueError("runtime bundle must be built on Linux x86_64")

    source_root = root / "source"
    wheelhouse = root / "wheelhouse"
    project_wheel = find_runtime_wheel(wheelhouse, "opportunity_os-")
    rendercv_wheel = find_runtime_wheel(wheelhouse, "rendercv-")
    typst_wheel = find_runtime_wheel(wheelhouse, "typst-")
    pymupdf_wheel = find_runtime_wheel(wheelhouse, "pymupdf-")
    typst_name = typst_wheel.name.casefold()
    if "manylinux" not in typst_name or "x86_64" not in typst_name:
        raise ValueError("typst runtime wheel must target Linux x86_64")

    return {
        "schema_version": _SCHEMA_VERSION,
        "git_sha": git_sha.lower(),
        "python": python_version,
        "platform": _TARGET_PLATFORM,
        "opportunity_os_version": _wheel_version(project_wheel, "opportunity_os-"),
        "rendercv_version": _wheel_version(rendercv_wheel, "rendercv-"),
        "typst_version": _wheel_version(typst_wheel, "typst-"),
        "pymupdf_version": _wheel_version(pymupdf_wheel, "pymupdf-"),
        "renderer_version": RENDERER_VERSION,
        "project_wheel": project_wheel.name,
        "project_wheel_sha256": _sha256_file(project_wheel),
        "typst_wheel": typst_wheel.name,
        "typst_wheel_sha256": _sha256_file(typst_wheel),
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
