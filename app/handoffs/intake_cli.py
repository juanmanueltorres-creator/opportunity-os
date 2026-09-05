from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from pydantic import ValidationError

from app.contributions.observations import ContributionPreview
from app.handoffs.models import QuestionResearchHandoff, ResearchOpportunityHandoff
from app.handoffs.preview import preview_research_opportunity_handoff
from app.handoffs.public_contribution_research import (
    build_public_contribution_candidate_handoff,
    render_research_opportunity_handoff_json,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.handoffs.intake_cli",
        description="Build and preview read-only cross-repository opportunity handoffs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_public = subparsers.add_parser("build-public-candidate")
    build_public.add_argument("--question-handoff-file", required=True)
    build_public.add_argument("--contribution-preview-file", required=True)
    build_public.add_argument("--handoff-id", required=True)
    build_public.add_argument("--created-at", required=True)
    build_public.add_argument("--out", required=True)

    preview = subparsers.add_parser("preview")
    preview.add_argument("--handoff-file", required=True)
    preview.add_argument("--out", required=True)
    preview.add_argument("--contribution-entry-id")
    preview.add_argument("--contribution-discovered-at")

    return parser


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _render_json(payload: dict) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def _blocked(error_code: str) -> int:
    print(json.dumps({"status": "BLOCKED", "errors": [error_code]}, sort_keys=True))
    return 2


def _run_build_public_candidate(args: argparse.Namespace) -> int:
    try:
        question_handoff = QuestionResearchHandoff.model_validate_json(
            Path(args.question_handoff_file).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError):
        return _blocked("invalid_question_handoff_file")

    try:
        contribution_preview = ContributionPreview.model_validate_json(
            Path(args.contribution_preview_file).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError):
        return _blocked("invalid_contribution_preview_file")

    try:
        handoff = build_public_contribution_candidate_handoff(
            question_handoff,
            contribution_preview,
            handoff_id=args.handoff_id,
            created_at=_parse_datetime(args.created_at),
        )
        rendered = render_research_opportunity_handoff_json(handoff)
    except (ValidationError, ValueError, TypeError):
        return _blocked("public_candidate_not_buildable")

    _write_text(Path(args.out), rendered)
    print(
        json.dumps(
            {
                "status": "BUILT",
                "handoff_id": handoff.handoff_id,
                "candidate_kind": handoff.candidate.kind,
            },
            sort_keys=True,
        )
    )
    return 0


def _run_preview(args: argparse.Namespace) -> int:
    try:
        handoff = ResearchOpportunityHandoff.model_validate_json(
            Path(args.handoff_file).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError):
        return _blocked("invalid_handoff_file")

    try:
        discovered_at = (
            _parse_datetime(args.contribution_discovered_at)
            if args.contribution_discovered_at is not None
            else None
        )
        preview = preview_research_opportunity_handoff(
            handoff,
            contribution_entry_id=args.contribution_entry_id,
            contribution_discovered_at=discovered_at,
        )
        rendered = _render_json(preview.model_dump(mode="json"))
    except (ValidationError, ValueError, TypeError):
        return _blocked("handoff_preview_not_buildable")

    _write_text(Path(args.out), rendered)
    print(
        json.dumps(
            {
                "status": preview.status,
                "handoff_id": preview.handoff_id,
                "candidate_kind": preview.candidate_kind,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "build-public-candidate":
        return _run_build_public_candidate(args)
    return _run_preview(args)


if __name__ == "__main__":
    raise SystemExit(main())
