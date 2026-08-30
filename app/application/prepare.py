from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Sequence

import pymupdf
from pydantic import ValidationError

from app.cv.loaders import load_evidence_catalog, load_master_facts
from app.cv.models import CVPolicy, PreparationResult, ValidationIssue
from app.cv.recruiter_policy import load_recruiter_policy
from app.cv.service import CVPreparationService
from app.radar.models import RadarAssessment
from app.radar.taxonomy import AliasRegistry, TaxonomyResolver

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALIAS_REGISTRY_PATH = _PROJECT_ROOT / "data" / "skill_aliases.yaml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.application.prepare",
        description="Prepare one evidence-safe recruiter CV and ApplicationPacket.",
    )
    parser.add_argument("--opportunity", required=True)
    parser.add_argument("--master-facts", required=True)
    parser.add_argument("--evidence-catalog", required=True)
    parser.add_argument("--recruiter-policy", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def _cv_policy() -> CVPolicy:
    return CVPolicy(
        language="en",
        required_identity_kinds=["identity", "contact"],
        required_sections=["projects", "skills"],
    )


def _load_assessment(path: str | Path) -> RadarAssessment:
    source = Path(path)
    try:
        payload = source.read_text(encoding="utf-8")
        return RadarAssessment.model_validate_json(payload)
    except (OSError, UnicodeError, ValidationError, ValueError) as exc:
        raise ValueError("invalid_radar_assessment") from exc


def _load_inputs(args: argparse.Namespace):
    try:
        master_facts = load_master_facts(args.master_facts)
        evidence_catalog = load_evidence_catalog(args.evidence_catalog)
    except ValueError as exc:
        raise ValueError("invalid_private_cv_input") from exc

    try:
        recruiter_policy = load_recruiter_policy(args.recruiter_policy)
    except ValueError as exc:
        raise ValueError("invalid_recruiter_policy") from exc

    try:
        alias_registry = AliasRegistry.load(_ALIAS_REGISTRY_PATH)
    except ValueError as exc:
        raise ValueError("invalid_taxonomy_config") from exc

    return master_facts, evidence_catalog, recruiter_policy, TaxonomyResolver(
        alias_registry=alias_registry
    )


def _issue_payload(issue: ValidationIssue) -> dict:
    return issue.model_dump(mode="json")


def _result_payload(
    result: PreparationResult,
    *,
    page_count: int | None = None,
) -> dict:
    packet = result.packet
    return {
        "status": result.status,
        "application_id": packet.application_id if packet is not None else None,
        "cv_pdf_path": packet.cv_pdf_path if packet is not None else None,
        "page_count": page_count,
        "cv_sha256": packet.cv_sha256 if packet is not None else None,
        "packet_sha256": packet.packet_sha256 if packet is not None else None,
        "unresolved_gaps": list(packet.unresolved_gaps) if packet is not None else [],
        "errors": [_issue_payload(issue) for issue in result.errors],
        "warnings": [_issue_payload(issue) for issue in result.warnings],
    }


def _error_payload(error: str) -> dict:
    return {
        "status": "ERROR",
        "application_id": None,
        "cv_pdf_path": None,
        "page_count": None,
        "cv_sha256": None,
        "packet_sha256": None,
        "unresolved_gaps": [],
        "error": error,
        "errors": [],
        "warnings": [],
    }


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _pdf_page_count(path: str | Path) -> int:
    document = pymupdf.open(path)
    try:
        return len(document)
    finally:
        document.close()


def _write_packet(result: PreparationResult) -> Path:
    packet = result.packet
    if packet is None:
        raise ValueError("prepared_result_missing_packet")
    destination = Path(packet.cv_pdf_path).with_name("application_packet.json")
    destination.write_text(
        json.dumps(
            packet.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        assessment = _load_assessment(args.opportunity)
    except ValueError:
        _print(_error_payload("invalid_radar_assessment"))
        return 2

    try:
        master_facts, evidence_catalog, recruiter_policy, resolver = _load_inputs(args)
    except ValueError as exc:
        _print(_error_payload(str(exc)))
        return 2

    service = CVPreparationService(
        taxonomy_resolver=resolver,
        recruiter_policy=recruiter_policy,
    )

    try:
        result = service.prepare(
            assessment=assessment,
            master_facts=master_facts,
            evidence_catalog=evidence_catalog,
            policy=_cv_policy(),
            output_root=args.output_root,
            now=datetime.now(timezone.utc),
        )
    except ValueError:
        _print(_error_payload("invalid_private_cv_input"))
        return 2

    if result.status != "PREPARED" or result.packet is None:
        _print(_result_payload(result))
        return 1

    try:
        page_count = _pdf_page_count(result.packet.cv_pdf_path)
        _write_packet(result)
    except (OSError, ValueError):
        _print(_error_payload("application_artifact_write_failed"))
        return 2

    _print(_result_payload(result, page_count=page_count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
