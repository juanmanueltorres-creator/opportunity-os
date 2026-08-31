from __future__ import annotations

import argparse
import os
from pathlib import Path

import pymupdf

from scripts.render_recruiter_previews import render_previews

_A4_WIDTH_POINTS = 595.276
_A4_HEIGHT_POINTS = 841.89
_A4_HEIGHT_ROUNDED_POINTS = 842
_PAGE_TOLERANCE_POINTS = 3.0


def verify_recruiter_pdf(path: Path) -> None:
    document = pymupdf.open(path)
    try:
        page_count = document.page_count
        if page_count != 1:
            raise RuntimeError(f"offline recruiter smoke expected one page, got {page_count}: {path}")

        page = document[0]
        if abs(float(page.rect.width) - _A4_WIDTH_POINTS) > _PAGE_TOLERANCE_POINTS:
            raise RuntimeError(f"offline recruiter smoke is not A4 width: {path}")
        if abs(float(page.rect.height) - _A4_HEIGHT_POINTS) > _PAGE_TOLERANCE_POINTS:
            raise RuntimeError(f"offline recruiter smoke is not A4 height: {path}")
        if round(float(page.rect.height)) != _A4_HEIGHT_ROUNDED_POINTS:
            raise RuntimeError(f"offline recruiter smoke has unexpected rounded A4 height: {path}")

        extracted_text = page.get_text().strip()
        if not extracted_text:
            raise RuntimeError(f"offline recruiter smoke has no selectable text: {path}")

        uris = {
            str(link.get("uri"))
            for link in page.get_links()
            if link.get("uri")
        }
        if not any(uri.startswith("mailto:") for uri in uris):
            raise RuntimeError(f"offline recruiter smoke has no mailto: URI: {path}")
        if not any(uri.startswith("https://") for uri in uris):
            raise RuntimeError(f"offline recruiter smoke has no https:// URI: {path}")
    finally:
        document.close()


def verify_runtime(output_dir: Path) -> list[Path]:
    source_root = Path(__file__).resolve().parents[1]
    previous_cwd = Path.cwd()
    os.chdir(source_root)
    try:
        outputs = render_previews(output_dir.resolve())
    finally:
        os.chdir(previous_cwd)

    if len(outputs) != 2:
        raise RuntimeError(f"offline recruiter smoke expected two fictional previews, got {len(outputs)}")
    for output in outputs:
        verify_recruiter_pdf(output)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the canonical recruiter renderer from a bundled offline runtime."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/ci/offline-runtime-smoke"),
    )
    args = parser.parse_args()

    for output in verify_runtime(args.output_dir):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
