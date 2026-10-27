"""Offline API tests for the additive Opportunity OS dashboard."""
from fastapi.testclient import TestClient
import pytest

from app import dashboard_api as dashboard

TOKEN = "dashboard-test-token-1234567890123456"
HEADERS = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_API_TOKEN", TOKEN)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    return TestClient(dashboard.app)


def test_dashboard_is_static_and_keeps_token_out_of_html(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "OPPORTUNITY / OS" in response.text
    assert TOKEN not in response.text
    assert 'localStorage' not in response.text.split("<script>")[-1].split("</script>")[0] or "nunca localStorage" in response.text
    assert "no-store" in response.headers["cache-control"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_status_requires_auth_and_never_returns_api_key(client, monkeypatch):
    assert client.get("/api/v1/dashboard/status").status_code == 401
    monkeypatch.setenv("GEMINI_API_KEY", "secret-must-never-leak")
    pending = client.get("/api/v1/dashboard/status", headers=HEADERS)
    assert pending.status_code == 200
    assert pending.json()["ai_configured"] is False
    assert pending.json()["model"] == "gemini-2.5-flash-lite"
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    response = client.get("/api/v1/dashboard/status", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["ai_configured"] is True
    assert "secret-must-never-leak" not in response.text


def test_analysis_requires_auth_and_server_key(client):
    body = {"opportunity_id": "job-1"}
    assert client.post("/api/v1/dashboard/ai-review", json=body).status_code == 401
    response = client.post("/api/v1/dashboard/ai-review", json=body, headers=HEADERS)
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_missing_opportunity_never_calls_gemini(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setattr(dashboard.storage, "_select", lambda sql, params: [])
    response = client.post("/api/v1/dashboard/ai-review",
                           json={"opportunity_id": "missing"}, headers=HEADERS)
    assert response.status_code == 404


def test_analysis_uses_stored_job_and_structured_response(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "local-fake-gemini-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    seen = {}

    def fake_select(sql, params):
        seen["sql"], seen["params"] = sql, params
        return [{"id": "job-1", "company": "Test", "title": "GIS Junior",
                 "description": "Uso de QGIS", "location": "Córdoba",
                 "source_url": "https://example.org/jobs/1",
                 "verification_status": "PENDING"}]

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{
                "text": '{"fit":"medio","recommendation":"revisar","summary":"Posible coincidencia",'
                        '"strengths":["QGIS"],"gaps":["Verificar requisitos"],'
                        '"caveat":"No se verificó si sigue abierta"}'
            }]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, headers, json):
            seen["url"], seen["headers"], seen["payload"] = url, headers, json
            return FakeResponse()

    monkeypatch.setattr(dashboard.storage, "_select", fake_select)
    monkeypatch.setattr(dashboard.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    response = client.post("/api/v1/dashboard/ai-review",
                           json={"opportunity_id": "job-1",
                                 "candidate_context": "Conocimiento de GIS"},
                           headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["fit"] == "medio"
    assert seen["params"] == ("job-1",)
    assert "WHERE id = %s" in seen["sql"]
    assert seen["url"].endswith("/models/gemini-2.5-flash-lite:generateContent")
    assert seen["headers"]["x-goog-api-key"] == "local-fake-gemini-key"
    assert "Conocimiento de GIS" in seen["payload"]["contents"][0]["parts"][0]["text"]


def test_review_input_is_bounded_and_rejects_extra_fields(client):
    too_long = {"opportunity_id": "test", "candidate_context": "x" * 2401}
    assert client.post("/api/v1/dashboard/ai-review", json=too_long, headers=HEADERS).status_code == 422
    extra = {"opportunity_id": "test", "new_field": "unexpected"}
    assert client.post("/api/v1/dashboard/ai-review", json=extra, headers=HEADERS).status_code == 422


def test_free_tier_gate_blocks_api_request_when_unconfirmed(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a-key-without-confirmed-free-project")
    response = client.post("/api/v1/dashboard/ai-review",
                           json={"opportunity_id": "job-1"}, headers=HEADERS)
    assert response.status_code == 503
    assert "Free Tier" in response.json()["detail"]


def test_paid_model_env_override_does_not_change_free_model(client, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-4-argon")
    response = client.get("/api/v1/dashboard/status", headers=HEADERS)
    assert response.json()["model"] == "gemini-2.5-flash-lite"
