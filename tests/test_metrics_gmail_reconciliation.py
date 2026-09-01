from datetime import datetime, timezone

from app.metrics.history import HistoricalObservation, SQLiteHistoricalRepository
from app.metrics.models import ReportWindow
from app.metrics.projection import reconcile_facts
from app.metrics.sources import read_historical_facts, read_relationship_facts
from app.relationships.models import RelationshipEvent
from app.relationships.repository import SQLiteRelationshipRepository

UTC = timezone.utc
WINDOW = ReportWindow(
    start=datetime(2026, 8, 1, tzinfo=UTC),
    end=datetime(2026, 9, 1, tzinfo=UTC),
)


def test_native_gmail_reply_reconciles_with_same_historical_provider_message(tmp_path):
    relationships_path = tmp_path / "relationships.sqlite3"
    relationships = SQLiteRelationshipRepository(relationships_path)
    relationships.initialize()
    relationships.append_event(
        RelationshipEvent(
            event_id="native-reply-1",
            account_id="account-1",
            kind="REPLIED",
            occurred_at=datetime(2026, 8, 23, tzinfo=UTC),
            source_ref="gmail:thread:t-1:message:r-1",
        )
    )

    history_path = tmp_path / "history.sqlite3"
    history = SQLiteHistoricalRepository(history_path)
    history.initialize()
    history.save_observation(
        HistoricalObservation(
            observation_id="historical-reply-1",
            kind="REPLY_OBSERVED",
            opportunity_id=None,
            account_id="account-1",
            company=None,
            occurred_at=datetime(2026, 8, 23, tzinfo=UTC),
            observed_at=datetime(2026, 8, 31, tzinfo=UTC),
            provenance="IMPORTED_GMAIL",
            provider_message_id="r-1",
            provider_thread_id="t-1",
            event_confidence=1.0,
            link_confidence=1.0,
        )
    )

    native = read_relationship_facts(relationships_path, WINDOW)
    historical = read_historical_facts(history_path, WINDOW)
    result = reconcile_facts(native.items, historical.facts)

    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.evidence_class == "NATIVE"
    assert fact.exact_anchor == "gmail-message:r-1"
    assert fact.thread_anchor == "gmail-thread:t-1"
