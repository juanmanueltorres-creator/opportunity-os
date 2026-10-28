"""Public ATS listing observations are not verified applications or private data."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from app.radar.source_evidence import source_evidence, observed_on_public_ats
from scripts.publish_public_snapshot import public_snapshot

T0 = "2026-10-28T12:23:00+00:00"
T1 = "2026-10-28T12:23:08+00:00"


def report(raw):
    return public_snapshot({"generated_at": T0, "atlas": [raw]})["atlas"][0]


def test_official_urls_are_strict_and_positive_only():
    assert observed_on_public_ats(source="ashby", source_url="https://jobs.ashbyhq.com/g2i/abc",
                                  source_id="abc")
    assert observed_on_public_ats(source="lever", source_url="https://jobs.lever.co/RyzLabs/a0",
                                  source_id="a0")
    assert observed_on_public_ats(source="greenhouse",
                                  source_url="https://job-boards.greenhouse.io/board/jobs/123",
                                  source_id="123")
    assert not observed_on_public_ats(source="greenhouse",
                                      source_url="https://job-boards.greenhouse.io/board/jobs/999",
                                      source_id="123")
    assert not observed_on_public_ats(source="ashby",
                                      source_url="https://jobs.ashbyhq.com.evil.test/g2i/abc",
                                      source_id="abc")
    assert not observed_on_public_ats(source="jobicy",
                                      source_url="https://jobicy.com/jobs/abc", source_id="abc")
    assert not observed_on_public_ats(source="ashby",
                                      source_url="https://jobs.ashbyhq.com@gitrecruit.evil/g2i/abc",
                                      source_id="abc")


def test_public_snapshot_keeps_exact_timestamp_for_genuine_at_board():
    job = SimpleNamespace(
        source="ashby", source_url="https://jobs.ashbyhq.com/g2i/abc",
        source_id="abc", discovered_at=datetime.fromisoformat(T1),
    )
    observed = source_evidence(job)
    assert observed["source_check"] == "LISTED_ON_PUBLIC_ATS"
    item = report({
        "id": "ashby:abc", "source": "ashby", "title": "GIS Engineer",
        "company": "G2i", "source_url": job.source_url, "source_checked_at": T1,
        "source_check": observed["source_check"], "private_token": "do-not-leak",
    })
    assert item["source_check"] == "LISTED_ON_PUBLIC_ATS"
    assert item["source_checked_at"] == T1
    assert "do-not-leak" not in json.dumps(item)


def test_no_false_ats_status_for_aggregators_or_old_claim():
    base = {
        "id": "ashby:abc", "source": "ashby",
        "title": "GIS Engineer", "company": "G2i",
        "source_url": "https://jobs.ashbyhq.com/g2i/abc",
        "source_check": "LISTED_ON_PUBLIC_ATS",
        "source_checked_at": "2026-10-26T12:23:08+00:00",
    }
    assert report(base)["source_check"] == "NOT_CHECKED"
    assert report({**base, "source": "jobicy", "id": "jobicy:abc",
                   "source_url": "https://jobicy.com/jobs/abc",
                   "source_checked_at": T1})["source_check"] == "NOT_CHECKED"
    assert report({**base, "source_url": "https://jobs.ashbyhq.com.evil.test/g2i/abc",
                   "source_checked_at": T1})["source_check"] == "NOT_CHECKED"
    assert report({**base, "source_check": "VERIFIED_OPEN",
                   "source_checked_at": T1})["source_check"] == "NOT_CHECKED"


def test_no_claims_from_missing_or_naive_capture_date():
    job = SimpleNamespace(
        source="lever", source_url="https://jobs.lever.co/RyzLabs/abc",
        source_id="abc", discovered_at=datetime(2026, 10, 28, 12, 23),
    )
    assert source_evidence(job)["source_check"] == "NOT_CHECKED"
    assert report({"id": "lever:abc", "source": "lever", "title": "Developer",
                   "company": "RYZ Labs", "source_url": job.source_url,
                   "source_check": "LISTED_ON_PUBLIC_ATS"})["source_check"] == "NOT_CHECKED"
