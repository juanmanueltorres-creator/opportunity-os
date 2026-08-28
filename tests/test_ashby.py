import json
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

import httpx
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "ashby_jobs.json"
NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _module():
    return import_module("app.connectors.ashby")


def _base():
    return import_module("app.connectors.base")


def test_ashby_normalizer_maps_public_job_board_payload() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    jobs = _module().AshbyConnector.normalize_payload(
        payload,
        company_name="Example Spatial Labs",
        discovered_at=NOW,
    )

    job = jobs[0]
    assert job.id == "ashby:123e4567-e89b-12d3-a456-426614174000"
    assert job.source == "ashby"
    assert job.source_url == "https://jobs.ashbyhq.com/example/123e4567-e89b-12d3-a456-426614174000"
    assert job.company == "Example Spatial Labs"
    assert job.title == "Geospatial Frontend Engineer"
    assert job.location == "Remote"
    assert job.remote_policy == "remote"
    assert job.description == "Build interactive mapping experiences."
    assert job.published_at.isoformat() == "2026-08-26T16:00:00+00:00"


@pytest.mark.asyncio
async def test_ashby_timeout_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = _module().AshbyConnector(
            client,
            board_name="example",
            company_name="Example Spatial Labs",
        )
        with pytest.raises(_base().ConnectorTimeoutError):
            await connector.fetch()


def test_ashby_skips_unlisted_public_postings() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["jobs"][0]["isListed"] = False

    jobs = _module().AshbyConnector.normalize_payload(
        payload,
        company_name="Example Spatial Labs",
        discovered_at=NOW,
    )

    assert jobs == []
