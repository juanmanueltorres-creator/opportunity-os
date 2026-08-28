import json
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

import httpx
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "lever_jobs.json"
NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _module():
    return import_module("app.connectors.lever")


def _base():
    return import_module("app.connectors.base")


def test_lever_normalizer_maps_public_posting_payload() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    jobs = _module().LeverConnector.normalize_payload(
        payload,
        company_name="Example Geo Co",
        discovered_at=NOW,
    )

    job = jobs[0]
    assert job.id == "lever:4f03aa00-1111-2222-3333-abc123abc123"
    assert job.source == "lever"
    assert job.company == "Example Geo Co"
    assert job.title == "Geospatial Backend Engineer"
    assert job.location == "Remote, Americas"
    assert job.remote_policy == "remote"
    assert job.description == "Develop spatial APIs."
    assert job.published_at is None


@pytest.mark.asyncio
async def test_lever_malformed_payload_is_typed_and_does_not_leak() -> None:
    secret = "lever-upstream-secret-text"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": secret}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = _module().LeverConnector(
            client,
            site="example",
            company_name="Example Geo Co",
        )
        with pytest.raises(_base().ConnectorPayloadError) as exc_info:
            await connector.fetch()

    assert secret not in str(exc_info.value)
