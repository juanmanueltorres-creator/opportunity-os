from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.contributions.bridge import ContributionObservationBridge
from app.contributions.github_provider import (
    GitHubPublicContributionProvider,
    selection_from_github_url,
)
from app.contributions.observations import (
    ContributionImportRequest,
    ContributionPreview,
)
from app.contributions.projector import ContributionProjector
from app.contributions.repository import SQLiteContributionRepository

DEFAULT_DB = Path("state/contributions.local.sqlite3")


def _clock() -> datetime:
    return datetime.now(timezone.utc)


class _NoNetworkProvider:
    def fetch(self, selection, *, captured_at):
        raise AssertionError("provider called during import")


def _build_preview_bridge(
    repository: SQLiteContributionRepository,
) -> tuple[ContributionObservationBridge, httpx.Client]:
    client = httpx.Client(
        base_url="https://api.github.com",
        timeout=20.0,
    )
    provider = GitHubPublicContributionProvider(
        client,
        token=os.getenv("GITHUB_TOKEN"),
    )
    return (
        ContributionObservationBridge(
            provider=provider,
            repository=repository,
            projector=ContributionProjector(),
            clock=_clock,
        ),
        client,
    )


def _build_import_bridge(
    repository: SQLiteContributionRepository,
) -> ContributionObservationBridge:
    return ContributionObservationBridge(
        provider=_NoNetworkProvider(),
        repository=repository,
        projector=ContributionProjector(),
        clock=_clock,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.contributions.intake_cli",
        description="Preview and confirm explicit public GitHub contribution facts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser("preview")
    preview.add_argument("--url", required=True)
    preview.add_argument("--operator-login", required=True)
    preview.add_argument("--entry-id")
    preview.add_argument("--db", default=str(DEFAULT_DB))
    preview.add_argument("--out", required=True)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--preview-file", required=True)
    import_parser.add_argument("--confirmed-by", required=True)
    import_parser.add_argument("--db", default=str(DEFAULT_DB))

    return parser


def _print_preview_summary(preview: ContributionPreview) -> None:
    print(
        json.dumps(
            {
                "status": preview.status,
                "entry_id": preview.entry_id,
                "source_ref": preview.source_ref,
            },
            sort_keys=True,
        )
    )


def _run_preview(args: argparse.Namespace) -> int:
    repository = SQLiteContributionRepository(Path(args.db))
    bridge, client = _build_preview_bridge(repository)
    try:
        selection = selection_from_github_url(
            args.url,
            operator_github_login=args.operator_login,
            entry_id=args.entry_id,
        )
        preview = bridge.preview(selection)
    except (ValueError, httpx.HTTPError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": type(exc).__name__}))
        return 2
    finally:
        client.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(preview.model_dump_json(indent=2), encoding="utf-8")
    _print_preview_summary(preview)
    return 0


def _run_import(args: argparse.Namespace) -> int:
    try:
        preview = ContributionPreview.model_validate_json(
            Path(args.preview_file).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError):
        print(json.dumps({"status": "BLOCKED", "errors": ["invalid_preview_file"]}))
        return 2

    if preview.status != "IMPORTABLE":
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "errors": ["preview_not_importable"],
                }
            )
        )
        return 2

    try:
        request = ContributionImportRequest(
            preview=preview,
            confirmed_by=args.confirmed_by,
            confirmed_at=_clock(),
        )
    except (ValidationError, ValueError):
        print(json.dumps({"status": "BLOCKED", "errors": ["invalid_confirmation"]}))
        return 2

    repository = SQLiteContributionRepository(Path(args.db))
    repository.initialize()
    bridge = _build_import_bridge(repository)
    result = bridge.import_preview(request)

    if result.status in {"IMPORTED", "ALREADY_IMPORTED"} and result.receipt is not None:
        print(result.receipt.model_dump_json(indent=2))
        return 0

    print(
        json.dumps(
            {
                "status": result.status,
                "errors": result.errors,
            },
            sort_keys=True,
        )
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "preview":
        return _run_preview(args)
    return _run_import(args)


if __name__ == "__main__":
    raise SystemExit(main())
