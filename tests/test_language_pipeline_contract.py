from __future__ import annotations

from datetime import datetime, timezone
import inspect
from types import SimpleNamespace

import pytest

from app.application.prepare import _parser
from app.cv.hashing import canonical_sha256
from app.cv.models import ApplicationPacket
from app.cv.service import CVPreparationService
from app.models.domain import Opportunity
from app.outreach.hashing import draft_semantic_payload
from app.outreach.models import DraftSnapshot
from app.outreach.preparation import application_packet_error
from app.outreach.service import OutreachService
from app.radar.models import LanguageDecision

NOW = datetime(2026, 8, 31, 4, 45, tzinfo=timezone.utc)


def _cli_args(*extra: str):
    return _parser().parse_args(
        [
            "--opportunity",
            "opp.json",
            "--master-facts",
            "facts.yaml",
            "--evidence-catalog",
            "evidence.yaml",
            "--recruiter-policy",
            "policy.yaml",
            "--output-root",
            "out",
            *extra,
        ]
    )


def test_canonical_cli_defaults_language_to_auto_and_accepts_override() -> None:
    assert _cli_args().language == "auto"
    assert _cli_args("--language", "es").language == "es"
    assert _cli_args("--language", "en").language == "en"


def test_canonical_cli_rejects_unknown_language() -> None:
    with pytest.raises(SystemExit):
        _cli_args("--language", "fr")


def test_application_packet_language_decision_is_required() -> None:
    field = ApplicationPacket.model_fields["language_decision"]
    assert field.is_required()


def test_cv_preparation_requires_explicit_language_decision_argument() -> None:
    parameter = inspect.signature(CVPreparationService.prepare).parameters[
        "language_decision"
    ]
    assert parameter.default is inspect.Parameter.empty


def test_draft_snapshot_language_is_required() -> None:
    field = DraftSnapshot.model_fields["language"]
    assert field.is_required()


def test_register_draft_requires_explicit_language_argument() -> None:
    parameter = inspect.signature(OutreachService.register_draft).parameters["language"]
    assert parameter.default is inspect.Parameter.empty


def test_draft_semantic_hash_payload_includes_language() -> None:
    snapshot = SimpleNamespace(
        opportunity_id="opp-1",
        brief_sha256="b" * 64,
        application_packet_sha256="p" * 64,
        reply_message_id=None,
        to=["recruiter@example.test"],
        cc=[],
        bcc=[],
        subject="Junior Software Engineer",
        body_canonical="Hi team, I am interested in the role. Thank you for your time.",
        attachments=[],
        cv_sha256="c" * 64,
        content_type="text/plain",
        language="en",
    )

    assert draft_semantic_payload(snapshot)["language"] == "en"


def test_packet_cv_language_mismatch_is_invalid() -> None:
    opportunity = Opportunity(
        id="opp-1",
        source="manual",
        source_id="fixture-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="Junior Software Engineer",
        description="We are looking for an engineer to join our team.",
        discovered_at=NOW,
    )
    assessment = SimpleNamespace(
        opportunity=opportunity,
        selected_intent="CAREER",
        best_career_track="tech",
        best_income_track="tech",
        scoring_version="score-v1",
        extractor_version="extract-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
    )
    packet = SimpleNamespace(
        opportunity_id="opp-1",
        opportunity_snapshot_hash=canonical_sha256(opportunity.model_dump(mode="json")),
        selected_intent="CAREER",
        application_track_id="tech",
        scoring_version="score-v1",
        extractor_version="extract-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
        language_decision=LanguageDecision(
            language="en",
            basis="posting_language",
            confidence=0.95,
            source_field="opportunity.title+description",
            source_text="English posting",
        ),
        cv_document=SimpleNamespace(language="es"),
    )

    assert application_packet_error(assessment, packet) == "packet_language_mismatch"


class _NoopRepository:
    def save_draft_snapshot(self, value):
        return value

    def list_events(self, opportunity_id):
        return []

    def append_event(self, value):
        return value


def _brief(language: str = "en"):
    return SimpleNamespace(
        opportunity_id="opp-1",
        brief_sha256="b" * 64,
        application_packet_sha256="p" * 64,
        contact_resolution=SimpleNamespace(email="recruiter@example.test"),
        cv_filename="cv.pdf",
        cv_sha256="c" * 64,
        language=language,
    )


def test_register_draft_rejects_declared_language_mismatch() -> None:
    service = OutreachService(repository=_NoopRepository())

    with pytest.raises(ValueError, match="draft_language_mismatch"):
        service.register_draft(
            brief=_brief("en"),
            provider_draft_id="draft-1",
            subject="Junior Software Engineer",
            body="Hi team, I am interested in the role. Thank you for your time.",
            language="es",
            content_type="text/plain",
            verification_basis="CREATED_EXACT",
            now=NOW,
        )


def test_register_draft_rejects_confident_text_language_mismatch() -> None:
    service = OutreachService(repository=_NoopRepository())

    with pytest.raises(ValueError, match="draft_text_language_mismatch"):
        service.register_draft(
            brief=_brief("en"),
            provider_draft_id="draft-1",
            subject="Postulación desarrollador",
            body=(
                "Hola equipo, vi la búsqueda y me interesa el puesto. "
                "Gracias por su tiempo y por considerar mi perfil."
            ),
            language="en",
            content_type="text/plain",
            verification_basis="CREATED_EXACT",
            now=NOW,
        )


def test_register_draft_allows_ambiguous_technical_text_when_declared_language_matches() -> None:
    service = OutreachService(repository=_NoopRepository())

    draft = service.register_draft(
        brief=_brief("en"),
        provider_draft_id="draft-technical",
        subject="Python / SQL / FastAPI",
        body="PostGIS, React, REST API, Docker, Git.",
        language="en",
        content_type="text/plain",
        verification_basis="CREATED_EXACT",
        now=NOW,
    )

    assert draft.language == "en"
    assert draft.body_canonical == "PostGIS, React, REST API, Docker, Git."
