"""PostgreSQL cutover wiring checks: no local SQLite and no unauthenticated access."""
from fastapi.testclient import TestClient
import pytest

from app import postgres_bootstrap as bootstrap

READ="postgresql://reader:secret@example.test/db"
WRITE="postgresql://writer:secret@example.test/db"
TOKEN="unit-test-token-1234567890123456789012345678"


def test_postgres_bootstrap_requires_both_dsns(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_DSN",raising=False)
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_WRITE_DSN",raising=False)
    with pytest.raises(RuntimeError,match="PostgreSQL write connection"):
        bootstrap.create_postgres_app()
    monkeypatch.setenv("OPPORTUNITY_POSTGRES_WRITE_DSN",WRITE)
    with pytest.raises(RuntimeError,match="PostgreSQL read connection"):
        bootstrap.create_postgres_app()


def test_postgres_bootstrap_never_constructs_sqlite_paths(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_POSTGRES_DSN",READ)
    monkeypatch.setenv("OPPORTUNITY_POSTGRES_WRITE_DSN",WRITE)
    monkeypatch.setenv("OPPORTUNITY_API_TOKEN",TOKEN)
    from app import main
    def reject_sqlite(*args,**kwargs):
        raise AssertionError("SQLite must not be instantiated in Postgres composition")
    monkeypatch.setattr(main,"SQLiteOpportunityRepository",reject_sqlite)
    monkeypatch.setattr(main,"SQLiteAvailabilityRepository",reject_sqlite)
    monkeypatch.setattr(main,"SQLiteCurationLedgerRepository",reject_sqlite)
    monkeypatch.setattr(main,"SQLiteEnrichmentRepository",reject_sqlite)
    monkeypatch.setattr(main,"_load_default_relationship_memory",reject_sqlite)
    app=bootstrap.create_postgres_app()
    client=TestClient(app)
    assert client.get("/health").status_code==200
    assert client.get("/api/v1/opportunities").status_code==401
    assert client.get("/storage/api/v1/summary").status_code==401
    assert client.get("/api/v1/opportunities",headers={"Authorization":"Bearer bad"}).status_code==401


def test_postgres_bootstrap_rejects_unset_api_token(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_POSTGRES_DSN",READ)
    monkeypatch.setenv("OPPORTUNITY_POSTGRES_WRITE_DSN",WRITE)
    monkeypatch.delenv("OPPORTUNITY_API_TOKEN",raising=False)
    app=bootstrap.create_postgres_app()
    response=TestClient(app).get("/api/v1/opportunities")
    assert response.status_code==503


def test_history_query_fails_closed_without_database(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_WRITE_DSN",raising=False)
    from app.repositories.postgres_history import PostgresApplicationHistory
    from app.models.domain import Opportunity
    from datetime import datetime, timezone
    job=Opportunity(id="1",source="test",source_id="1",source_url="https://example.org/job",
      company="Example",title="Analyst",description="Example",discovered_at=datetime.now(timezone.utc))
    with pytest.raises(RuntimeError,match="no SQLite fallback"):
        PostgresApplicationHistory().was_applied(job)


def test_postgres_history_sql_limits_to_company_and_role(monkeypatch):
    from app.repositories import postgres_history as history
    from datetime import datetime,timezone
    from app.models.domain import Opportunity
    observed=[]
    class Cur:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def execute(self,sql,params):
            observed.append((sql,params))
        def fetchone(self):return {"applied":True}
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def cursor(self):return Cur()
    monkeypatch.setattr(history,"_connect",lambda:Conn())
    job=Opportunity(id="1",source="x",source_id="x",source_url="https://example.org",
      company="Example",title="Analyst",description="Example",
      discovered_at=datetime(2026,10,26,tzinfo=timezone.utc))
    assert history.PostgresApplicationHistory().was_applied(job)
    sql,params=observed[0]
    assert "a.company" in sql and "a.role_title" in sql
    assert params[:2]==("Example","Analyst")
