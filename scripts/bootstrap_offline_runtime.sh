#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
EXPECTED_SHA="${2:?usage: bootstrap_offline_runtime.sh <bundle-root> <expected-git-sha>}"
BUNDLE_ROOT="$(cd "$BUNDLE_ROOT" && pwd)"
MANIFEST="$BUNDLE_ROOT/runtime_manifest.json"
CHECKSUMS="$BUNDLE_ROOT/SHA256SUMS"
WHEELHOUSE="$BUNDLE_ROOT/wheelhouse"
SOURCE_ROOT="$BUNDLE_ROOT/source"
VENV="$BUNDLE_ROOT/.venv"

fail() {
  printf 'offline runtime bootstrap failed: %s\n' "$1" >&2
  exit 2
}

test -f "$MANIFEST" || fail "missing runtime_manifest.json"
test -f "$CHECKSUMS" || fail "missing SHA256SUMS"
test -d "$WHEELHOUSE" || fail "missing wheelhouse"
test -d "$SOURCE_ROOT" || fail "missing source tree"

# Verify every bundled byte before executing or installing bundle contents.
(
  cd "$BUNDLE_ROOT"
  sha256sum -c SHA256SUMS
) || fail "checksum verification failed"

python - "$MANIFEST" "$EXPECTED_SHA" "$SOURCE_ROOT" "$WHEELHOUSE" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
expected_sha = sys.argv[2].lower()
source_root = Path(sys.argv[3])
wheelhouse = Path(sys.argv[4])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

manifest_sha = str(manifest.get("git_sha", "")).lower()
if manifest_sha != expected_sha:
    raise SystemExit(
        f"manifest git SHA mismatch: expected {expected_sha}, artifact has {manifest_sha}"
    )

current_python = f"{sys.version_info.major}.{sys.version_info.minor}"
manifest_python = str(manifest.get("python", ""))
if current_python != manifest_python:
    raise SystemExit(
        f"Python runtime mismatch: interpreter={current_python}, artifact={manifest_python}"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()

if sha256_tree(source_root) != manifest.get("source_sha256"):
    raise SystemExit("source tree hash does not match runtime manifest")

for name_key, hash_key in (
    ("project_wheel", "project_wheel_sha256"),
    ("typst_wheel", "typst_wheel_sha256"),
):
    name = str(manifest.get(name_key, ""))
    path = wheelhouse / name
    if not name or not path.is_file():
        raise SystemExit(f"manifest references missing wheel: {name_key}={name!r}")
    if sha256_file(path) != manifest.get(hash_key):
        raise SystemExit(f"wheel hash does not match runtime manifest: {name}")
PY

rm -rf "$VENV"
python -m venv "$VENV"
PYTHON="$VENV/bin/python"

export PIP_NO_INDEX=1
export PIP_DISABLE_PIP_VERSION_CHECK=1

PROJECT_WHEEL="$($PYTHON - "$MANIFEST" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["project_wheel"])
PY
)"

"$PYTHON" -m pip install \
  --no-index \
  --find-links "$WHEELHOUSE" \
  "$WHEELHOUSE/$PROJECT_WHEEL"

# Execute the checked, SHA-bound source tree rather than relying on package-data
# lookup inside the wheel. The renderer resolves config/data relative to source.
export PYTHONPATH="$SOURCE_ROOT"

"$PYTHON" - "$MANIFEST" <<'PY'
from __future__ import annotations

import importlib.metadata
import json
import sys

import pymupdf
import rendercv
import typst

from app.cv.renderers.rendercv_typst import RENDERER_VERSION

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
checks = {
    "opportunity_os_version": importlib.metadata.version("opportunity-os"),
    "rendercv_version": importlib.metadata.version("rendercv"),
    "typst_version": importlib.metadata.version("typst"),
    "pymupdf_version": importlib.metadata.version("PyMuPDF"),
    "renderer_version": RENDERER_VERSION,
}
for key, actual in checks.items():
    expected = str(manifest.get(key, ""))
    if actual != expected:
        raise SystemExit(f"runtime version mismatch for {key}: expected {expected}, got {actual}")

# Imports above are intentional runtime checks; retain references so static tools
# do not treat them as accidental.
assert rendercv is not None and typst is not None and pymupdf is not None
PY

SMOKE_DIR="$BUNDLE_ROOT/.runtime-smoke"
rm -rf "$SMOKE_DIR"
(
  cd "$SOURCE_ROOT"
  "$PYTHON" scripts/verify_offline_runtime.py --output-dir "$SMOKE_DIR"
)

printf 'offline runtime verified: sha=%s python=%s\n' \
  "$EXPECTED_SHA" \
  "$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
