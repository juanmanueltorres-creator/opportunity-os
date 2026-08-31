from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.cv.models import ApplicationPacket, ClaimProvenance, CVClaim, CVDocumentModel
from app.cv.recruiter_models import RecruiterDocumentModel, TechnologyGroup
from app.radar.models import LanguageDecision

NOW = datetime(2026, 8, 31, 5, 20, tzinfo=timezone.utc)


def _document() -> CVDocumentModel:
    return CVDocumentModel(
        document_version="cvdoc-v1",
        language="en",
        claims=[
            CVClaim(
                claim_id="skill-python",
                section="skills",
                kind="skill",
                text="Python",
            )
        ],
        entries=[],
        provenance_map={
            "skill-python": ClaimProvenance(fact_ids=["fact-python"]),
        },
    )


def _recruiter_document() -> RecruiterDocumentModel:
    return RecruiterDocumentModel(
        source_cv_document_version="cvdoc-v1",
        language="en",
        identity_claim_id="skill-python",
        headline_claim_id="skill-python",
        technology_groups=[
            TechnologyGroup(
                label_id="software_data",
                skill_claim_ids=["skill-python"],
            )
        ],
    )


def _packet_payload() -> dict:
    return {
        "application_id": "app-language-contract",
        "opportunity_id": "opp-language-contract",
        "opportunity_snapshot_hash": "a" * 64,
        "selected_intent": "CAREER",
        "application_track_id": "tech",
        "career_match": 88.0,
        "income_viability": 75.0,
        "confidence_score": 90.0,
        "scoring_version": "score-v1",
        "extractor_version": "extract-v1",
        "alias_registry_version": "aliases-v1",
        "taxonomy_versions": {},
        "master_facts_version": "b" * 64,
        "evidence_catalog_version": "c" * 64,
        "composer_version": "composer-v1",
        "cv_document_version": "cvdoc-v1",
        "recruiter_policy_version": "recruiter-policy-v1",
        "renderer_version": "rendercv-typst-v1",
        "selected_fact_ids": ["fact-python"],
        "selected_evidence_ids": [],
        "unresolved_gaps": [],
        "language_decision": LanguageDecision(
            language="es",
            basis="explicit_override",
            confidence=1.0,
            source_field="cli.language",
            source_text="es",
        ),
        "cv_document": _document(),
        "recruiter_document": _recruiter_document(),
        "cv_pdf_path": "artifacts/applications/app-language-contract/cv.pdf",
        "cv_sha256": "d" * 64,
        "packet_sha256": "e" * 64,
        "created_at": NOW,
    }


def test_application_packet_rejects_language_decision_cv_mismatch() -> None:
    with pytest.raises(ValidationError, match="packet language decision must match CV document language"):
        ApplicationPacket.model_validate(_packet_payload())
