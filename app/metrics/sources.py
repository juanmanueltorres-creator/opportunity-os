from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Generic, Literal, TypeVar

from app.cv.models import ApplicationPacket
from app.metrics.history import HistoricalImportBatch, HistoricalObservation
from app.metrics.models import Coverage, ReportWindow
from app.models.domain import Opportunity
from app.outreach.models import DraftSnapshot, SendReceipt
from app.radar.models import DailyRadarBatch
from app.relationships.models import RelationshipEvent

T = TypeVar("T")

EvidenceClass = Literal["NATIVE", "IMPORTED_PROVIDER", "MANUAL"]
MetricFactKind = Literal[
    "PACKET_PREPARED",
    "DRAFT",
    "SEND",
    "REPLY",
    "PROCESS_OPENED",
    "PROCESS_CLOSED",
]


@dataclass(frozen=True)
class SourceRead(Generic[T]):
    items: tuple[T, ...]
    coverage: Coverage
    basis: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpportunityFact:
    opportunity_id: str
    discovered_at: datetime


@dataclass(frozen=True)
class QualificationFact:
    opportunity_id: str
    tier: Literal["HIGH", "MEDIUM", "STRETCH", "DISCARD"]
    observed_at: datetime
    scoring_version: str


@dataclass(frozen=True)
class MetricFact:
    fact_id: str
    kind: MetricFactKind
    opportunity_id: str | None
    account_id: str | None
    occurred_at: datetime
    evidence_class: EvidenceClass
    exact_anchor: str | None
    link_confidence: float
    draft_sha256: str | None = None
    thread_anchor: str | None = None


@dataclass(frozen=True)
class HistoricalRead:
    facts: tuple[MetricFact, ...]
    batches: tuple[HistoricalImportBatch, ...]
    coverage: Coverage
    basis: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _within(window: ReportWindow, value: datetime) -> bool:
    return window.start <= value <= window.end


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _missing_source(name: str, path: Path) -> SourceRead[T]:
    return SourceRead(
        items=(),
        coverage="UNKNOWN",
        basis=(),
        warnings=(f"{name} source missing: {path}",),
    )


def read_opportunity_facts(
    path: str | Path,
    window: ReportWindow,
) -> SourceRead[OpportunityFact]:
    path = Path(path)
    if not path.exists():
        return _missing_source("opportunity_db", path)

    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT id, source, source_id, source_url, company, title, description,
                   discovered_at, status, location, remote_policy, published_at,
                   required_skills, preferred_skills, compensation
            FROM opportunities
            ORDER BY discovered_at ASC, id ASC
            """
        ).fetchall()

    facts: list[OpportunityFact] = []
    for row in rows:
        payload = dict(row)
        payload["required_skills"] = json.loads(payload["required_skills"])
        payload["preferred_skills"] = json.loads(payload["preferred_skills"])
        opportunity = Opportunity.model_validate(payload)
        if _within(window, opportunity.discovered_at):
            facts.append(
                OpportunityFact(
                    opportunity_id=opportunity.id,
                    discovered_at=opportunity.discovered_at,
                )
            )

    return SourceRead(
        items=tuple(facts),
        coverage="COMPLETE",
        basis=("opportunity_db",),
    )


def read_application_facts(
    root: str | Path,
    window: ReportWindow,
) -> SourceRead[MetricFact]:
    root = Path(root)
    if not root.exists():
        return _missing_source("applications_root", root)

    facts: list[MetricFact] = []
    warnings: list[str] = []
    for path in sorted(root.glob("*/application_packet.json")):
        try:
            packet = ApplicationPacket.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"invalid application packet: {path.name}: {exc.__class__.__name__}")
            continue
        if packet.status != "PREPARED" or not _within(window, packet.created_at):
            continue
        facts.append(
            MetricFact(
                fact_id=f"packet:{packet.packet_sha256}",
                kind="PACKET_PREPARED",
                opportunity_id=packet.opportunity_id,
                account_id=None,
                occurred_at=packet.created_at,
                evidence_class="NATIVE",
                exact_anchor=f"packet:{packet.packet_sha256}",
                link_confidence=1.0,
            )
        )

    return SourceRead(
        items=tuple(facts),
        coverage="PARTIAL" if warnings else "COMPLETE",
        basis=("application_packets",),
        warnings=tuple(warnings),
    )


def read_outreach_facts(
    path: str | Path,
    window: ReportWindow,
) -> SourceRead[MetricFact]:
    path = Path(path)
    if not path.exists():
        return _missing_source("outreach_db", path)

    with _connect_readonly(path) as conn:
        draft_rows = conn.execute(
            """
            SELECT payload_json
            FROM outreach_snapshots
            WHERE entity_type = 'draft_snapshot'
            ORDER BY created_at ASC, entity_key ASC
            """
        ).fetchall()
        send_rows = conn.execute(
            """
            SELECT payload_json
            FROM send_receipts
            ORDER BY sent_at ASC, receipt_id ASC
            """
        ).fetchall()

    facts: list[MetricFact] = []
    warnings: list[str] = []
    for row in draft_rows:
        try:
            draft = DraftSnapshot.model_validate_json(row["payload_json"])
        except Exception as exc:
            warnings.append(f"invalid outreach draft snapshot: {exc.__class__.__name__}")
            continue
        if not _within(window, draft.created_at):
            continue
        facts.append(
            MetricFact(
                fact_id=f"draft:{draft.draft_snapshot_id}",
                kind="DRAFT",
                opportunity_id=draft.opportunity_id,
                account_id=None,
                occurred_at=draft.created_at,
                evidence_class="NATIVE",
                exact_anchor=f"draft:{draft.draft_sha256}",
                link_confidence=1.0,
                draft_sha256=draft.draft_sha256,
            )
        )

    for row in send_rows:
        try:
            receipt = SendReceipt.model_validate_json(row["payload_json"])
        except Exception as exc:
            warnings.append(f"invalid send receipt: {exc.__class__.__name__}")
            continue
        if not _within(window, receipt.sent_at):
            continue
        facts.append(
            MetricFact(
                fact_id=f"send:{receipt.receipt_id}",
                kind="SEND",
                opportunity_id=receipt.opportunity_id,
                account_id=None,
                occurred_at=receipt.sent_at,
                evidence_class="NATIVE",
                exact_anchor=f"gmail-message:{receipt.provider_message_id}",
                link_confidence=1.0,
                draft_sha256=receipt.draft_sha256,
                thread_anchor=(
                    f"gmail-thread:{receipt.provider_thread_id}"
                    if receipt.provider_thread_id
                    else None
                ),
            )
        )

    facts.sort(key=lambda item: (item.occurred_at, item.fact_id))
    return SourceRead(
        items=tuple(facts),
        coverage="PARTIAL" if warnings else "COMPLETE",
        basis=("outreach_db",),
        warnings=tuple(warnings),
    )


def read_relationship_facts(
    path: str | Path,
    window: ReportWindow,
) -> SourceRead[MetricFact]:
    path = Path(path)
    if not path.exists():
        return _missing_source("relationships_db", path)

    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT payload_json
            FROM relationship_events
            WHERE kind IN ('REPLIED', 'PROCESS_OPENED', 'PROCESS_CLOSED')
            ORDER BY occurred_at ASC, event_id ASC
            """
        ).fetchall()

    kind_map: dict[str, MetricFactKind] = {
        "REPLIED": "REPLY",
        "PROCESS_OPENED": "PROCESS_OPENED",
        "PROCESS_CLOSED": "PROCESS_CLOSED",
    }
    facts: list[MetricFact] = []
    warnings: list[str] = []
    for row in rows:
        try:
            event = RelationshipEvent.model_validate_json(row["payload_json"])
        except Exception as exc:
            warnings.append(f"invalid relationship event: {exc.__class__.__name__}")
            continue
        if not _within(window, event.occurred_at):
            continue
        source_ref = (event.source_ref or "").strip()
        exact_anchor = (
            f"source:{source_ref}" if source_ref else f"native-relationship-event:{event.event_id}"
        )
        facts.append(
            MetricFact(
                fact_id=f"relationship:{event.event_id}",
                kind=kind_map[event.kind],
                opportunity_id=None,
                account_id=event.account_id,
                occurred_at=event.occurred_at,
                evidence_class="NATIVE",
                exact_anchor=exact_anchor,
                link_confidence=1.0,
            )
        )

    return SourceRead(
        items=tuple(facts),
        coverage="PARTIAL" if warnings else "COMPLETE",
        basis=("relationships_db",),
        warnings=tuple(warnings),
    )


def read_radar_facts(
    root: str | Path,
    window: ReportWindow,
) -> SourceRead[QualificationFact]:
    root = Path(root)
    if not root.exists():
        return _missing_source("radar_history", root)

    facts: list[QualificationFact] = []
    warnings: list[str] = []
    for path in sorted(root.rglob("*.json")):
        try:
            batch = DailyRadarBatch.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"invalid radar artifact: {path.name}: {exc.__class__.__name__}")
            continue
        if not _within(window, batch.generated_at):
            continue
        for assessment in batch.items:
            if assessment.tier is None:
                continue
            facts.append(
                QualificationFact(
                    opportunity_id=assessment.opportunity.id,
                    tier=assessment.tier,
                    observed_at=batch.generated_at,
                    scoring_version=batch.scoring_version,
                )
            )

    facts.sort(key=lambda item: (item.observed_at, item.opportunity_id, item.tier))
    return SourceRead(
        items=tuple(facts),
        coverage="PARTIAL",
        basis=("radar_artifacts",),
        warnings=tuple(warnings),
    )


def _historical_exact_anchor(observation: HistoricalObservation) -> str | None:
    if observation.provider_message_id:
        return f"gmail-message:{observation.provider_message_id}"
    source_ref = (observation.source_ref or "").strip()
    if source_ref:
        return f"source:{source_ref}"
    return None


def _historical_kind(kind: str) -> MetricFactKind:
    mapping: dict[str, MetricFactKind] = {
        "DRAFT_OBSERVED": "DRAFT",
        "SEND_OBSERVED": "SEND",
        "REPLY_OBSERVED": "REPLY",
        "PROCESS_OPENED_OBSERVED": "PROCESS_OPENED",
        "PROCESS_CLOSED_OBSERVED": "PROCESS_CLOSED",
    }
    return mapping[kind]


def _history_coverage(
    batches: tuple[HistoricalImportBatch, ...],
    window: ReportWindow,
) -> Coverage:
    if not batches:
        return "PARTIAL"
    for batch in batches:
        if (
            batch.selection_scope == "ALL_DECLARED_OUTREACH_THREADS"
            and batch.complete_for_declared_scope
            and batch.window_start <= window.start
            and batch.window_end >= window.end
        ):
            return "COMPLETE"
    return "PARTIAL"


def read_historical_facts(
    path: str | Path,
    window: ReportWindow,
) -> HistoricalRead:
    path = Path(path)
    if not path.exists():
        return HistoricalRead(
            facts=(),
            batches=(),
            coverage="UNKNOWN",
            warnings=(f"history_db source missing: {path}",),
        )

    with _connect_readonly(path) as conn:
        observation_rows = conn.execute(
            """
            SELECT payload_json
            FROM historical_observations
            ORDER BY occurred_at ASC, observation_id ASC
            """
        ).fetchall()
        batch_rows = conn.execute(
            """
            SELECT payload_json
            FROM historical_import_batches
            ORDER BY completed_at ASC, batch_id ASC
            """
        ).fetchall()

    warnings: list[str] = []
    observations: list[HistoricalObservation] = []
    for row in observation_rows:
        try:
            observation = HistoricalObservation.model_validate_json(row["payload_json"])
        except Exception as exc:
            warnings.append(f"invalid historical observation: {exc.__class__.__name__}")
            continue
        if _within(window, observation.occurred_at):
            observations.append(observation)

    batches: list[HistoricalImportBatch] = []
    for row in batch_rows:
        try:
            batches.append(HistoricalImportBatch.model_validate_json(row["payload_json"]))
        except Exception as exc:
            warnings.append(f"invalid historical import batch: {exc.__class__.__name__}")

    facts = tuple(
        MetricFact(
            fact_id=f"historical:{observation.observation_id}",
            kind=_historical_kind(observation.kind),
            opportunity_id=observation.opportunity_id,
            account_id=observation.account_id,
            occurred_at=observation.occurred_at,
            evidence_class=(
                "IMPORTED_PROVIDER"
                if observation.provenance == "IMPORTED_GMAIL"
                else "MANUAL"
            ),
            exact_anchor=_historical_exact_anchor(observation),
            link_confidence=observation.link_confidence,
            thread_anchor=(
                f"gmail-thread:{observation.provider_thread_id}"
                if observation.provider_thread_id
                else None
            ),
        )
        for observation in observations
    )
    batch_tuple = tuple(batches)
    coverage = _history_coverage(batch_tuple, window)
    if warnings and coverage == "COMPLETE":
        coverage = "PARTIAL"
    return HistoricalRead(
        facts=facts,
        batches=batch_tuple,
        coverage=coverage,
        basis=("historical_observations",),
        warnings=tuple(warnings),
    )
