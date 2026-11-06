"""Public-only daily snapshot difference contract."""
import json
import pytest
from scripts.compare_public_snapshots import compare_public_snapshots

AT_OLD = "2026-11-04T12:00:00+00:00"
AT_NEW = "2026-11-05T12:00:00+00:00"

def snap(date, rows):
    return {"schema_version": 1, "generated_at": date, "atlas": rows}

def job(id_, **extra):
    return {"id": id_, "source_url": "https://example.org/jobs/" + id_,
            "company": "Empresa " + id_, "title": "GIS Analyst",
            "remote_mode": "REMOTE", "argentina_eligible": "UNKNOWN", **extra}

def test_deterministic_counts_and_absent_is_not_closed():
    old = snap(AT_OLD, [job("kept"), job("gone")])
    new = snap(AT_NEW, [job("kept"), job("arrived")])
    diff = compare_public_snapshots(old, new)
    assert diff["available"] is True
    assert (diff["newly_observed_count"], diff["no_longer_observed_count"],
            diff["continuing_count"]) == (1, 1, 1)
    assert [j["id"] for j in diff["new_jobs"]] == ["arrived"]
    assert [j["id"] for j in diff["no_longer_observed_jobs"]] == ["gone"]
    assert "does NOT prove a vacancy closed" in diff["caution"]

def test_private_metadata_never_crosses_public_boundary():
    source = job("id", email="user@example.org", private_notes="VERY PRIVATE",
                 contact="phone", application={"private": True})
    diff = compare_public_snapshots(snap(AT_OLD, []), snap(AT_NEW, [source]))
    out = json.dumps(diff)
    assert diff["newly_observed_count"] == 1
    for sensitive in ["user@example.org", "VERY PRIVATE", "phone", "application"]:
        assert sensitive not in out

def test_no_baseline_is_not_a_fake_new_job_surge():
    diff = compare_public_snapshots(None, snap(AT_NEW, [job("one")]))
    assert diff["available"] is False
    assert diff["newly_observed_count"] is None
    assert diff["new_jobs"] == []

def test_invalid_timestamps_fail_closed():
    diff = compare_public_snapshots(snap(AT_NEW, [job("prior")]), snap(AT_NEW, [job("new")]))
    assert diff["available"] is False
    with pytest.raises(ValueError):
        compare_public_snapshots(snap(AT_OLD, []), snap("bad timestamp", [job("new")]))

def test_unsafe_rows_and_duplicates_cannot_change_counts():
    a = job("a")
    current = snap(AT_NEW, [a, a, job("x", source_url="http://example.org/x"), {"id": "bad"}])
    diff = compare_public_snapshots(snap(AT_OLD, []), current)
    assert diff["current_count"] == diff["newly_observed_count"] == 1
