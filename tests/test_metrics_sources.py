from __future__ import annotations

from datetime import datetime, timezone

from app.cv.models import ApplicationPacket, ClaimProvenance, CVClaim, CVDocumentModel
from app.cv.recruiter_models import RecruiterDocumentModel, TechnologyGroup
from app.metrics.history import HistoricalImportBatch, HistoricalObservation, SQLiteHistoricalRepository
from app.metrics.models import ReportWindow
from app.metrics.sources import (
    read_application_facts,
    read_historical_facts,
    read_opportunity_facts,
    read_outreach_facts,
    read_radar_facts,
    read_relationship_facts,
)
from app.models.domain import Opportunity
from app.outreach.models import DraftAttachment, DraftSnapshot, SendReceipt
from app.outreach.repository import SQLiteOutreachRepository
from app.radar.models import LanguageDecision
from app.relationships.models import RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository
from app.repositories.opportunities import SQLiteOpportunityRepository

UTC = timezone.utc
START = datetime(2026, 8, 1, tzinfo=UTC)
END = datetime(2026, 9, 1, tzinfo=UTC)
WINDOW = ReportWindow(start=START, end=END)


def _opportunity(opportunity_id: str, discovered_at: datetime) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        source="manual",
        source_id=f"source-{opportunity_id}",
        source_url=f"https://example.test/{opportunity_id}",
        company="Example Labs",
        title="Software Engineer",
        description="Build reliable systems.",
        discovered_at=discovered_at,
        required_skills=["Python"],
    )


def _packet() -> ApplicationPacket:
    document = CVDocumentModel(
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
    recruiter_document = RecruiterDocumentModel(
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
    return ApplicationPacket(
        application_id="app-1",
        opportunity_id="opp-in",
        opportunity_snapshot_hash="a" * 64,
        selected_intent="CAREER",
        application_track_id="tech",
        career_match=88.0,
        income_viability=75.0,
        confidence_score=90.0,
        scoring_version="score-v1",
        extractor_version="extract-v1",
        alias_registry_version="aliases-v1",
        taxonomy_versions={},
        master_facts_version="b" * 64,
        evidence_catalog_version="c" * 64,
        composer_version="composer-v1",
        cv_document_version="cvdoc-v1",
        recruiter_policy_version="recruiter-policy-v1",
        renderer_version="rendercv-typst-v1",
        selected_fact_ids=["fact-python"],
        selected_evidence_ids=[],
        unresolved_gaps=[],
        language_decision=LanguageDecision(
            language="en",
            basis="explicit_override",
            confidence=1.0,
            source_field="fixture",
            source_text="en",
        ),
        cv_document=document,
        recruiter_document=recruiter_document,
        cv_pdf_path="artifacts/applications/app-1/cv.pdf",
        cv_sha256="d" * 64,
        packet_sha256="e" * 64,
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )


def _draft() -> DraftSnapshot:
    cv_sha = "d" * 64
    return DraftSnapshot(
        draft_snapshot_id="draft-snapshot-1",
        opportunity_id="opp-in",
        brief_sha256="a" * 64,
        application_packet_sha256="e" * 64,
        provider_draft_id="gmail-draft-1",
        to=["recruiter@example.test"],
        subject="Application",
        body_canonical="Hello, this is a test application.",
        language="en",
        attachments=[DraftAttachment(filename="cv.pdf", sha256=cv_sha, role="CV")],
        cv_sha256=cv_sha,
        content_type="text/plain",
        verification_basis="CREATED_EXACT",
        draft_sha256="f" * 64,
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        verified_at=datetime(2026, 8, 21, tzinfo=UTC),
    )


def _send() -> SendReceipt:
    return SendReceipt(
        receipt_id="receipt-1",
        opportunity_id="opp-in",
        approval_id="approval-1",
        send_request_id="request-1",
        draft_sha256="f" * 64,
        application_packet_sha256="e" * 64,
        idempotency_key="1" * 64,
        provider_message_id="gmail-message-1",
        provider_thread_id="gmail-thread-1",
        recipient="recruiter@example.test",
        sent_at=datetime(2026, 8, 22, tzinfo=UTC),
    )


def test_missing_optional_sqlite_source_is_not_created(tmp_path):
    missing = tmp_path / "missing" / "outreach.sqlite3"
    result = read_outreach_facts(missing, WINDOW)

    assert result.coverage == "UNKNOWN"
    assert result.items == ()
    assert not missing.exists()
    assert not missing.parent.exists()


def test_missing_application_and_radar_roots_are_not_created(tmp_path):
    applications = tmp_path / "applications"
    radar = tmp_path / "radar"

    assert read_application_facts(applications, WINDOW).coverage == "UNKNOWN"
    assert read_radar_facts(radar, WINDOW).coverage == "UNKNOWN"
    assert not applications.exists()
    assert not radar.exists()


def test_opportunity_source_uses_persisted_first_discovery_time(tmp_path):
    path = tmp_path / "opportunities.sqlite3"
    repository = SQLiteOpportunityRepository(path)
    repository.initialize()
    repository.upsert(_opportunity("opp-before", datetime(2026, 7, 31, tzinfo=UTC)))
    repository.upsert(_opportunity("opp-in", datetime(2026, 8, 15, tzinfo=UTC)))
    repository.upsert(_opportunity("opp-after", datetime(2026, 9, 2, tzinfo=UTC)))

    result = read_opportunity_facts(path, WINDOW)

    assert result.coverage == "COMPLETE"
    assert [item.opportunity_id for item in result.items] == ["opp-in"]
    assert result.items[0].discovered_at == datetime(2026, 8, 15, tzinfo=UTC)


def test_application_source_counts_only_typed_prepared_packets(tmp_path):
    root = tmp_path / "applications"
    valid_dir = root / "app-1"
    invalid_dir = root / "broken"
    valid_dir.mkdir(parents=True)
    invalid_dir.mkdir(parents=True)
    (valid_dir / "application_packet.json").write_text(_packet().model_dump_json(), encoding="utf-8")
    (invalid_dir / "application_packet.json").write_text('{"status":"PREPARED"}', encoding="utf-8")

    result = read_application_facts(root, WINDOW)

    assert len(result.items) == 1
    assert result.items[0].kind == "PACKET_PREPARED"
    assert result.items[0].opportunity_id == "opp-in"
    assert result.coverage == "PARTIAL"
    assert any("invalid application packet" in warning for warning in result.warnings)


def test_outreach_source_maps_verified_draft_and_confirmed_send(tmp_path):
    path = tmp_path / "outreach.sqlite3"
    repository = SQLiteOutreachRepository(path)
    repository.initialize()
    repository.save_draft_snapshot(_draft())
    repository.save_send_receipt(_send())

    result = read_outreach_facts(path, WINDOW)

    assert result.coverage == "COMPLETE"
    by_kind = {item.kind: item for item in result.items}
    assert by_kind["DRAFT"].exact_anchor == f"draft:{'f' * 64}"
    assert by_kind["SEND"].exact_anchor == "gmail-message:gmail-message-1"
    assert by_kind["SEND"].thread_anchor == "gmail-thread:gmail-thread-1"
    assert by_kind["SEND"].draft_sha256 == "f" * 64


def test_relationship_source_maps_only_outcome_events(tmp_path):
    path = tmp_path / "relationships.sqlite3"
    repository = SQLiteRelationshipRepository(path)
    repository.initialize()
    repository.append_event(
        RelationshipEvent(
            event_id="note-1",
            account_id="account-1",
            kind="NOTE_RECORDED",
            occurred_at=datetime(2026, 8, 22, tzinfo=UTC),
            source_ref="note:1",
        )
    )
    repository.append_event(
        RelationshipEvent(
            event_id="reply-1",
            account_id="account-1",
            kind="REPLIED",
            occurred_at=datetime(2026, 8, 23, tzinfo=UTC),
            source_ref="gmail-message:reply-1",
        )
    )
    repository.append_event(
        RelationshipEvent(
            event_id="process-1",
            account_id="account-1",
            kind="PROCESS_OPENED",
            occurred_at=datetime(2026, 8, 24, tzinfo=UTC),
            source_ref="calendar:event-1",
        )
    )

    result = read_relationship_facts(path, WINDOW)

    assert result.coverage == "COMPLETE"
    assert [item.kind for item in result.items] == ["REPLY", "PROCESS_OPENED"]
    assert result.items[0].exact_anchor == "source:gmail-message:reply-1"


def test_historical_source_preserves_provenance_and_declared_coverage(tmp_path):
    path = tmp_path / "history.sqlite3"
    repository = SQLiteHistoricalRepository(path)
    repository.initialize()
    repository.save_batch(
        HistoricalImportBatch(
            batch_id="august-selected",
            provider="GMAIL",
            window_start=START,
            window_end=END,
            selection_scope="SELECTED_THREADS",
            selected_message_count=1,
            selected_thread_count=1,
            completed_at=END,
            complete_for_declared_scope=True,
        )
    )
    repository.save_observation(
        HistoricalObservation(
            observation_id="hist-reply-1",
            kind="REPLY_OBSERVED",
            opportunity_id=None,
            account_id="account-1",
            company="Example Labs",
            occurred_at=datetime(2026, 8, 23, tzinfo=UTC),
            observed_at=END,
            provenance="IMPORTED_GMAIL",
            provider_message_id="reply-1",
            provider_thread_id="gmail-thread-1",
            event_confidence=1.0,
            link_confidence=0.0,
        )
    )

    result = read_historical_facts(path, WINDOW)

    assert result.coverage == "PARTIAL"
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.kind == "REPLY"
    assert fact.evidence_class == "IMPORTED_PROVIDER"
    assert fact.exact_anchor == "gmail-message:reply-1"
    assert fact.thread_anchor == "gmail-thread:gmail-thread-1"
    assert fact.link_confidence == 0.0
    assert len(result.batches) == 1


def test_missing_history_db_is_read_only(tmp_path):
    path = tmp_path / "missing" / "history.sqlite3"
    result = read_historical_facts(path, WINDOW)

    assert result.coverage == "UNKNOWN"
    assert result.facts == ()
    assert not path.exists()
    assert not path.parent.exists()
