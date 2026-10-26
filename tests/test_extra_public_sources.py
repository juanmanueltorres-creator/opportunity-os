"""Contract tests for four additional documented, public job APIs.

All inputs are synthetic: no network, credentials or real candidate data.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.radar.extra_public_sources import (
    parse_jobicy, parse_himalayas, parse_remoteok, parse_arbeitnow,
    collect_extended_sources, epoch_date,
)
from app.radar.source_catalog import load_source_catalog
from pathlib import Path

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def test_jobicy_parses_canonical_source_location_and_date():
    payload={"jobs":[{
      "id":123, "url":"https://jobicy.com/jobs/sample123", "jobTitle":"Analista de datos",
      "companyName":"Example Labs", "jobGeo":"Latin America",
      "jobDescription":"<p>Python <strong>SQL</strong></p>",
      "pubDate":"2026-10-25T10:00:00+00:00",
      "salaryMin":2000,"salaryMax":2600,"salaryCurrency":"USD","salaryPeriod":"monthly"
    },{
      "id":124,"url":"https://evil.invalid/job/1",
      "jobTitle":"Backend Developer","companyName":"Mismatched"
    }]}
    items=parse_jobicy(payload,NOW)
    assert len(items)==1
    assert items[0].source=="jobicy"
    assert items[0].location=="Latin America"
    assert items[0].description=="Python SQL"
    assert "monthly" in items[0].compensation
    assert items[0].published_at==datetime(2026,10,25,10,tzinfo=timezone.utc)


def test_himalayas_preserves_application_link_country_and_expiry():
    now=int(NOW.timestamp())
    payload={"jobs":[{
      "guid":"https://himalayas.app/companies/test/jobs/developer",
      "applicationLink":"https://himalayas.app/companies/test/jobs/developer",
      "title":"GIS Developer","companyName":"Remote Test",
      "description":"<p>QGIS and PostGIS</p>",
      "locationRestrictions":[{"alpha2":"AR","name":"Argentina"},{"alpha2":"CL","name":"Chile"}],
      "pubDate":now-3600,"expiryDate":now+86400
    },{
      "guid":"old","applicationLink":"https://himalayas.app/companies/test/jobs/old",
      "title":"Software Engineer","companyName":"Expired",
      "pubDate":now-86400,"expiryDate":now-1
    }]}
    items=parse_himalayas(payload,NOW)
    assert len(items)==1
    assert items[0].source=="himalayas"
    assert items[0].location=="Argentina, Chile"
    assert items[0].source_url==payload["jobs"][0]["applicationLink"]
    assert items[0].published_at==datetime.fromtimestamp(now-3600,tz=timezone.utc)


def test_epoch_parser_accepts_sec_and_ms_and_not_fake_bool():
    seconds=int(NOW.timestamp())
    assert epoch_date(seconds)==NOW
    assert epoch_date(seconds*1000)==NOW
    assert epoch_date(True) is None


def test_remoteok_ignores_first_terms_notice_and_unsafe_urls():
    payload=[
        {"legal":"Please link back to Remote OK"},
        {"id":"88","company":"Startup Example","position":"Product Manager",
         "description":"<p>Responsable de producto</p>", "location":"LATAM",
         "url":"https://remoteok.com/remote-jobs/88",
         "epoch":int(NOW.timestamp())-3600},
        {"id":"99","company":"Suspicious","position":"Python",
         "url":"javascript:alert(1)"}
    ]
    items=parse_remoteok(payload,NOW)
    assert len(items)==1
    assert items[0].source=="remoteok"
    assert items[0].title=="Product Manager"


def test_arbeitnow_remote_field_is_boolean_not_truthiness():
    payload={"data":[{
       "slug":"geospatial-analyst","company_name":"Example",
       "title":"Geospatial Analyst","remote":True,
       "location":"Argentina", "url":"https://www.arbeitnow.com/view/geospatial-analyst",
       "description":"<p>Remote GIS</p>","created_at":int(NOW.timestamp())
    },{
       "slug":"web-designer","company_name":"Berlin Co",
       "title":"Web Designer","remote":False,
       "location":"Berlin","url":"https://www.arbeitnow.com/view/web-designer",
       "description":"Design"
    }]}
    items=parse_arbeitnow(payload,NOW)
    assert len(items)==2
    assert items[0].remote_policy=="remote"
    assert items[1].remote_policy=="onsite"


def test_parsers_fail_closed_on_schema_drift():
    for parser in (parse_jobicy,parse_himalayas,parse_arbeitnow):
        with pytest.raises(ValueError,match="schema mismatch"):
            parser({"data":"invalid","jobs":{}},NOW)
    with pytest.raises(ValueError,match="schema mismatch"):
        parse_remoteok({"jobs":[]},NOW)


@pytest.mark.asyncio
async def test_broken_source_does_not_stop_other_sources():
    seen=[]
    def handler(request: httpx.Request)->httpx.Response:
        host=request.url.host
        seen.append(host)
        if "jobicy.com" in host:
            return httpx.Response(503, text="Unavailable")
        if "himalayas.app" in host:
            return httpx.Response(200,json={"jobs":[{"guid":"abc","applicationLink":
               "https://himalayas.app/companies/a/jobs/b","title":"Backend Developer",
               "companyName":"Example","pubDate":int(NOW.timestamp())}]})
        if "remoteok.com" in host:
            return httpx.Response(200,json=[{"legal":"terms"}])
        if "arbeitnow.com" in host:
            return httpx.Response(200,json={"data":[]})
        raise AssertionError(host)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs,diag=await collect_extended_sources(client,now=NOW)
    assert len(seen)==4
    assert len(jobs)==1 and jobs[0].source=="himalayas"
    assert diag["jobicy"].startswith("ERROR")
    assert diag["himalayas"].startswith("OK")
    assert diag["remoteok"].startswith("OK")
    assert diag["arbeitnow"].startswith("OK")


def test_public_sources_present_in_catalog_and_verification_required():
    catalog=load_source_catalog(Path(__file__).resolve().parents[1]/"config/source_catalog.yaml")
    for key in ("jobicy","himalayas","remoteok","arbeitnow"):
        entry=catalog.resolve(key)
        assert entry is not None
        assert entry.authority=="DIRECT_PLATFORM"
        assert entry.verification_required
