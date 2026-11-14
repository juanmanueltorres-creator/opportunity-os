"""Fail-closed relationship persistence and order checks (no live credentials)."""
import pytest
from app.relationships import postgres_repository as pg


def test_postgres_connection_never_falls_back_to_sqlite(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_WRITE_DSN",raising=False)
    with pytest.raises(RuntimeError,match="no SQLite fallback"):
        pg.PostgresRelationshipRepository().initialize()


def test_identical_event_and_conflict():
    class Event:
        event_id="event-one"
        account_id="account-one"
        occurred_at="2026-10-26"
    cur=object()
    event=Event()
    original=pg.PostgresRelationshipRepository._event
    try:
        pg.PostgresRelationshipRepository._event=staticmethod(lambda cur,id:event)
        assert pg.PostgresRelationshipRepository._validate(cur,event)=="IDENTICAL"
        class Other:
            event_id="event-one"
            account_id="different"
        with pytest.raises(ValueError,match="event_id conflict"):
            pg.PostgresRelationshipRepository._validate(cur,Other())
    finally:
        pg.PostgresRelationshipRepository._event=original


def test_preferred_contact_cannot_be_unavailable(monkeypatch):
    class Account:
        preferred_next_contact_id="contact-one"
    class Contact:
        account_id="account-one"
        active=False
        disposition="HELD"
    monkeypatch.setattr(pg.PostgresRelationshipRepository,"_contact",staticmethod(lambda cur,id:Contact()))
    account=Account()
    account.account_id="account-one"
    with pytest.raises(ValueError,match="preferred contact"):
        pg.PostgresRelationshipRepository._save_account(object(),account)


def test_projector_exception_prevents_event_insert(monkeypatch):
    events=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):events.append(sql)
        def fetchone(self):return None
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr(pg,"_connect",lambda:Conn())
    monkeypatch.setattr(pg.PostgresRelationshipRepository,"_account",staticmethod(lambda *args:None))
    monkeypatch.setattr(pg.PostgresRelationshipRepository,"_contacts",staticmethod(lambda *args:[]))
    class Event:
        account_id="account-one"
        event_id="evt"
        occurred_at="2026-10-26"
    with pytest.raises(ValueError,match="projection failed"):
        pg.PostgresRelationshipRepository().apply_event_transaction(
            Event(),lambda account,contacts:(_ for _ in ()).throw(ValueError("projection failed")))
    assert not any("insert into opportunity_os.relationship_events" in q for q in events)
