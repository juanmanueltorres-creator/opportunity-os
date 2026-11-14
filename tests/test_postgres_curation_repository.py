"""Offline tests for the PostgreSQL curation ledger."""
import pytest
from app.curation import postgres_repository as pg

def test_no_local_fallback(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_WRITE_DSN",raising=False)
    with pytest.raises(RuntimeError,match="no SQLite fallback"):
        pg.PostgresCurationLedgerRepository().initialize()

def test_reject_invalid_limit():
    for value in (0,101):
        with pytest.raises(ValueError,match="1..100"):
            pg.PostgresCurationLedgerRepository().list_run_payload_json(limit=value)

def test_publication_compare_and_swap_fails_without_writes(monkeypatch):
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):statements.append(sql)
        def fetchone(self):return {"n":3}
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr(pg,"_connect",lambda:Conn())
    assert pg.PostgresCurationLedgerRepository().record_publication_if_count_unchanged(
        object(),expected_publication_count=2) is False
    assert not any("insert into" in statement.lower() for statement in statements)
