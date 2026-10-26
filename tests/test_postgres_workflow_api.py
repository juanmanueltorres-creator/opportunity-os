"""Offline contract tests for the PostgreSQL-only workflow API."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient

from app import postgres_workflow_api as workflow

TOKEN="test-token-1234567890123456789012345678"
HEAD={"Authorization":"Bearer "+TOKEN}

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_API_TOKEN",TOKEN)
    return TestClient(workflow.app)

def test_auth_enforced(client):
    assert client.post("/api/v1/history/applications",json={}).status_code==401
    assert client.post("/api/v1/source/refresh",json={"source":"remotive"}).status_code==401

def test_application_requires_evidence_and_is_idempotent(client,monkeypatch):
    seen=[]
    def fake_write(sql,params,**kwargs):
        seen.append((sql,params))
        return {"application_key":"api-example"}
    monkeypatch.setattr(workflow,"_write",fake_write)
    payload={"company":"Example Ltd","role_title":"Analyst","channel":"GMAIL_DIRECT",
      "status":"SENT","event_at":"2026-10-26T10:00:00Z",
      "source_reference":"https://example.com/proof"}
    a=client.post("/api/v1/history/applications",json=payload,headers=HEAD)
    b=client.post("/api/v1/history/applications",json=payload,headers=HEAD)
    assert a.status_code==200 and b.status_code==200
    assert seen[0][1][0]==seen[1][1][0]
    assert "on conflict(application_key)" in seen[0][0]
    invalid=client.post("/api/v1/history/applications",
      json={**payload,"event_at":"2026-10-26T10:00:00"},headers=HEAD)
    assert invalid.status_code==422

def test_manual_job_never_verifies_from_remote_label(client,monkeypatch):
    seen=[]
    def fake_write(sql,params,**kwargs):
        seen.append((sql,params))
        return {"id":"manual:example","created":True}
    monkeypatch.setattr(workflow,"_write",fake_write)
    payload={"source":"manual","source_id":"123","source_url":"https://example.com/job",
      "company":"Example","title":"Python","description":"Role description",
      "remote_policy":"remote"}
    r=client.post("/api/v1/opportunities/manual",json=payload,headers=HEAD)
    assert r.status_code==200
    assert "verification_status" not in seen[0][0]
    assert seen[0][1][9]=="REMOTE"
    bad=client.post("/api/v1/opportunities/manual",json={**payload,"source_url":"http://example.com"},headers=HEAD)
    assert bad.status_code==422

def test_verification_requires_confirmed_evidence(client,monkeypatch):
    calls=[]
    monkeypatch.setattr(workflow,"_write",lambda sql,params,**kwargs:(calls.append((sql,params)) or {"id":"j1"}))
    bad=client.post("/api/v1/opportunities/j1/verify",json={
      "observation_type":"VERIFIED_OPEN","source_url":"http://example.org",
      "evidence_source":"human","confirmed_by":"operator"},headers=HEAD)
    assert bad.status_code==422
    good=client.post("/api/v1/opportunities/j1/verify",json={
      "observation_type":"VERIFIED_CLOSED","source_url":"https://example.org/job",
      "evidence_source":"official","confirmed_by":"operator"},headers=HEAD)
    assert good.status_code==200 and len(calls)==1
    assert "availability_observations" in calls[0][0]

def test_unknown_refresh_source_is_rejected(client):
    r=client.post("/api/v1/source/refresh",json={"source":"not_registered"},headers=HEAD)
    assert r.status_code==422

def test_writer_missing_fails_closed(client,monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_WRITE_DSN",raising=False)
    r=client.post("/api/v1/history/applications",json={
      "company":"Example","role_title":"Analyst","channel":"ATS","status":"APPLIED",
      "event_at":"2026-10-26T10:00:00Z","source_reference":"https://example.org/proof"
    },headers=HEAD)
    assert r.status_code==503
