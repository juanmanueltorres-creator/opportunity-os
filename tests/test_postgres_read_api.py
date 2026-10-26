"""Tests for the isolated, fail-closed Postgres API (no live secrets needed)."""

from fastapi.testclient import TestClient
import pytest

from app import postgres_read_api as api

TOKEN = "local-test-token-1234567890-1234567890"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_API_TOKEN", TOKEN)
    return TestClient(api.app)


def test_no_configured_token_fails_closed(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_API_TOKEN", raising=False)
    c = TestClient(api.app)
    assert c.get("/api/v1/sources").status_code == 503


def test_private_routes_require_exact_bearer_token(client):
    assert client.get("/api/v1/sources").status_code == 401
    assert client.get("/api/v1/sources", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_liveness_does_not_claim_db_connectivity(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_DSN", raising=False)
    c = TestClient(api.app)
    assert c.get("/healthz").json() == {
        "status": "ok", "storage": "postgres-only"
    }


def test_db_missing_is_unavailable_without_fallback(client, monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_DSN", raising=False)
    response = client.get(
        "/api/v1/summary", headers={"Authorization": "Bearer " + TOKEN}
    )
    assert response.status_code == 503
    assert "PostgreSQL" in response.json()["detail"]


def test_sources_queries_private_schema(client, monkeypatch):
    observed = {}

    def fake_select(sql, params=()):
        observed["sql"] = sql
        observed["params"] = params
        return [{"source_key": "startupjobs_ar", "connector_status": "NOT_CONFIGURED"}]

    monkeypatch.setattr(api, "_select", fake_select)
    res = client.get(
        "/api/v1/sources?limit=5", headers={"Authorization": "Bearer " + TOKEN}
    )
    assert res.status_code == 200
    assert res.json()[0]["source_key"] == "startupjobs_ar"
    assert "opportunity_os.sources" in observed["sql"]
    assert observed["params"] == (5,)


def test_filters_parameterized_and_do_not_exclude_all_company_roles(client, monkeypatch):
    observed = {}

    def fake_select(sql, params=()):
        observed["sql"] = sql
        observed["params"] = params
        return []

    monkeypatch.setattr(api, "_select", fake_select)
    response = client.get(
        "/api/v1/opportunities",
        params={
            "keyword": "SQL' OR 1=1 --",
            "source": "startupjobs_ar",
            "remote_mode": "REMOTE",
            "argentina_eligible": "YES",
            "work_language": "ES",
            "verification_status": "VERIFIED",
            "since": "2026-10-14",
            "limit": 15,
            "offset": 5,
        },
        headers={"Authorization": "Bearer " + TOKEN},
    )
    assert response.status_code == 200
    assert "SQL' OR 1=1 --" not in observed["sql"]
    assert "%SQL' OR 1=1 --%" in observed["params"]
    assert "lower(trim(a.company)) = lower(trim(o.company))" in observed["sql"]
    assert "lower(trim(coalesce(a.role_title, ''))) = lower(trim(o.title))" in observed["sql"]
    assert "opportunity_os.opportunities" in observed["sql"]
    assert observed["params"][-2:] == (15, 5)


def test_outreach_does_not_expose_contact_email(client, monkeypatch):
    def fake_select(sql, params=()):
        assert "contact_email" not in sql
        return [{"company_or_project": "Example", "raw_status": "SENT"}]

    monkeypatch.setattr(api, "_select", fake_select)
    response = client.get(
        "/api/v1/history/outreach", headers={"Authorization": "Bearer " + TOKEN}
    )
    assert response.status_code == 200
    assert "contact_email" not in response.text


def test_query_limits_validated(client):
    res = client.get("/api/v1/opportunities?limit=999",
                     headers={"Authorization": "Bearer " + TOKEN})
    assert res.status_code == 422
