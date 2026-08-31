#!/usr/bin/env bash
set -euo pipefail

EXPECTED_SHA="${1:?usage: build_offline_runtime.sh <git-sha> [output-dir]}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
ACTUAL_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
OUTPUT_DIR="${2:-$REPO_ROOT/artifacts/ci/offline-runtime}"
BUNDLE_ROOT="$OUTPUT_DIR/opportunity-os-runtime"
WHEELHOUSE="$BUNDLE_ROOT/wheelhouse"
ARCHIVE_PATH="$OUTPUT_DIR/opportunity-os-runtime-linux-x86_64-py312.zip"

if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  printf 'Runtime bundle SHA mismatch: expected %s, checked out %s\n' "$EXPECTED_SHA" "$ACTUAL_SHA" >&2
  exit 2
fi

python - <<'PY'
import platform
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"offline runtime build requires Python 3.12, got {sys.version.split()[0]}")
if platform.system().lower() != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
    raise SystemExit("offline runtime build requires Linux x86_64")
PY

rm -rf "$OUTPUT_DIR"
mkdir -p "$WHEELHOUSE"

# Build the exact project wheel and every production dependency as wheels.
# The online build stage may use package indexes; the verification stage may not.
python -m pip wheel \
  --wheel-dir "$WHEELHOUSE" \
  --only-binary=:all: \
  "$REPO_ROOT"

python - "$REPO_ROOT" "$BUNDLE_ROOT" "$EXPECTED_SHA" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
bundle = Path(sys.argv[2]).resolve()
git_sha = sys.argv[3]
sys.path.insert(0, str(repo))

from scripts.runtime_bundle import (  # noqa: E402
    build_runtime_manifest,
    copy_runtime_source,
    find_runtime_wheel,
    write_sha256sums,
)

copy_runtime_source(repository_root=repo, destination=bundle / "source")

# Fail closed if the compiler/runtime wheels we depend on are not uniquely present.
project_wheel = find_runtime_wheel(bundle / "wheelhouse", "opportunity_os-")
typst_wheel = find_runtime_wheel(bundle / "wheelhouse", "typst-")
find_runtime_wheel(bundle / "wheelhouse", "rendercv-")
find_runtime_wheel(bundle / "wheelhouse", "pymupdf-")
if "manylinux" not in typst_wheel.name.casefold() or "x86_64" not in typst_wheel.name.casefold():
    raise SystemExit(f"unexpected typst runtime wheel: {typst_wheel.name}")
if "editable" in project_wheel.name.casefold():
    raise SystemExit("runtime bundle must contain a non-editable Opportunity OS wheel")

bootstrap_source = repo / "scripts" / "bootstrap_offline_runtime.sh"
if not bootstrap_source.is_file():
    raise SystemExit("scripts/bootstrap_offline_runtime.sh is required before building the bundle")
bootstrap_target = bundle / "bootstrap_offline.sh"
bootstrap_target.write_bytes(bootstrap_source.read_bytes())
bootstrap_target.chmod(0o755)

manifest = build_runtime_manifest(
    root=bundle,
    git_sha=git_sha,
    built_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
)
(bundle / "runtime_manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
write_sha256sums(bundle, bundle / "SHA256SUMS")
PY

python - "$OUTPUT_DIR" <<'PY'
import shutil
import sys
from pathlib import Path
output = Path(sys.argv[1]).resolve()
archive_base = output / "opportunity-os-runtime-linux-x86_64-py312"
archive = Path(shutil.make_archive(str(archive_base), "zip", root_dir=output, base_dir="opportunity-os-runtime"))
print(archive)
PY

test -f "$ARCHIVE_PATH"
printf '%s\n' "$ARCHIVE_PATH"
