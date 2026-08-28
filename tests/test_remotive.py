import json
from datetime import timezone
from importlib import import_module
from pathlib import Path

import httpx
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "remotive_jobs.json"


def _remotive_module():
    return import_module("app.connectors.remotive")


def _base_module():
    return import_module("app.connectors.base")


@pytest.mark.asyncio
async def test_remotive_fetch_normalizes_public_job_payload() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    observed_timeout = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_timeout.update(request.extensions["timeout"])
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await _remotive_module().RemotiveConnector(
            client=client, timeout_seconds=3.0
        ).fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "remotive:123456"
    assert job.source == "remotive"
    assert job.source_id == "123456"
    assert job.source_url == payload["jobs"][0]["url"]
    assert job.company == "Example Mapping Co"
    assert job.title == "Geospatial Developer"
    assert job.location == "Worldwide"
    assert job.remote_policy == "remote"
    assert job.description == "<p>Build geospatial tools with Python and web APIs.</p>"
    assert job.compensation == "$80,000 - $100,000"
    assert job.published_at.isoformat() == "2026-08-27T12:30:00+00:00"
    assert job.published_at.tzinfo == timezone.utc
    assert job.discovered_at.tzinfo is not None
    assert job.required_skills == []
    assert job.preferred_skills == []
    assert observed_timeout["read"] == 3.0


@pytest.mark.asyncio
async def test_remotive_timeout_becomes_typed_connector_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = _remotive_module().RemotiveConnector(client, timeout_seconds=2.0)
        with pytest.raises(_base_module().ConnectorTimeoutError):
            await connector.fetch()


@pytest.mark.asyncio
async def test_remotive_rejects_malformed_jobs_payload_without_echoing_it() -> None:
    secret = "do-not-echo-private-upstream-data"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": {"secret": secret}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = _remotive_module().RemotiveConnector(client)
        with pytest.raises(_base_module().ConnectorPayloadError) as exc_info:
            await connector.fetch()

    assert secret not in str(exc_info.value)
