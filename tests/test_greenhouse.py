import json
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

import httpx
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_jobs.json"
NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _module():
    return import_module("app.connectors.greenhouse")


def _base():
    return import_module("app.connectors.base")


def test_greenhouse_normalizer_maps_public_board_payload() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    jobs = _module().GreenhouseConnector.normalize_payload(
        payload,
        company_name="Example Mining Tech",
        discovered_at=NOW,
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "greenhouse:4012345"
    assert job.source == "greenhouse"
    assert job.source_id == "4012345"
    assert job.source_url == "https://boards.greenhouse.io/example/jobs/4012345"
    assert job.company == "Example Mining Tech"
    assert job.title == "GIS Software Engineer"
    assert job.location == "Remote - Americas"
    assert job.remote_policy == "remote"
    assert job.description == "<p>Build mapping services with Python.</p>"
    assert job.published_at is None
    assert job.discovered_at == NOW


@pytest.mark.asyncio
async def test_greenhouse_timeout_is_typed_and_uses_board_endpoint() -> None:
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = _module().GreenhouseConnector(
            client,
            board_token="example",
            company_name="Example Mining Tech",
            timeout_seconds=4.0,
        )
        with pytest.raises(_base().ConnectorTimeoutError):
            await connector.fetch()

    assert observed["url"] == "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
