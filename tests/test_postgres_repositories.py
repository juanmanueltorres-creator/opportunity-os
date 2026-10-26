"""Postgres repositories never open SQLite and preserve key model contracts."""
from datetime import datetime, timezone
from unittest.mock import patch
import pytest

from app.models.domain import Opportunity
from app.repositories import postgres as pg

NOW=datetime(2026,10,26,12,tzinfo=timezone.utc)

def example_job():
    return Opportunity(id="example:1",source="example",source_id="1",
       source_url="https://example.org/job/1",company="Example",title="Developer",
       description="Example job",discovered_at=NOW)

def test_connection_fails_closed(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_WRITE_DSN",raising=False)
    with pytest.raises(RuntimeError,match="no SQLite fallback"):
        pg.PostgresOpportunityRepository().initialize()

def test_upsert_uses_transaction_and_dedupe(monkeypatch):
    class Cursor:
        def __init__(self):self.executed=[]
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def execute(self,sql,params=None):self.executed.append((sql,params))
        def fetchone(self):
            if "returning *" in self.executed[-1][0]:
                return example_job().model_dump()|{"dedupe_key":"example|developer|"}
            return None
    class Connection:
        def __init__(self):self.cursor_obj=Cursor()
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def cursor(self):return self.cursor_obj
    c=Connection()
    monkeypatch.setattr(pg,"_connect",lambda:c)
    got,created=pg.PostgresOpportunityRepository().upsert(example_job())
    assert created and got.id=="example:1"
    assert "pg_advisory_xact_lock" in c.cursor_obj.executed[0][0]
    assert "opportunity_os.opportunities" in c.cursor_obj.executed[-1][0]
    assert "on conflict" not in c.cursor_obj.executed[-1][0].lower()

def test_radar_date_validations():
    r=pg.PostgresOpportunityRepository()
    with pytest.raises(ValueError,match="timezone-aware"):
        r.list_radar_candidates(now=datetime(2026,10,26),lookback_days=7)
    with pytest.raises(ValueError,match="non-negative"):
        r.list_radar_candidates(now=NOW,lookback_days=-1)

def test_verified_availability_cannot_invent_human_evidence():
    with pytest.raises(ValueError,match="explicit confirmed_by"):
        pg.PostgresAvailabilityRepository().record_verification(
            "example:1",is_open=True,observed_at=NOW,
            evidence_source="test",source_url="https://example.org")

def test_enrichment_version_validation():
    from app.radar.models import OpportunityEnrichment
    assert hasattr(pg.PostgresEnrichmentRepository,"save")
