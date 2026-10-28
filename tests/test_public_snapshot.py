"""Public feed contract: no private data leaks to the Vercel static site."""
import json

from scripts.publish_public_snapshot import public_snapshot


def test_public_json_allowlist_and_excludes_contacts():
    source = {
        "generated_at": "2026-10-28T14:00:00+00:00",
        "raw_jobs_seen": 200,
        "sources": {"getonbrd": "OK (10 parsed)"},
        "persistence": {"dsn": "SUPERSECRET"},
        "applications": [{"email": "private@example.test"}],
        "atlas": [{
            "id": "job-1",
            "company": "Startup",
            "title": "Python Junior",
            "source_url": "https://jobs.example.com/1",
            "source": "ashby",
            "track": "software_ai",
            "location": "LATAM",
            "score": 74,
            "search_lane": "REVIEW",
            "candidate_email": "private@example.test",
            "private_notes": "Do not publish",
            "cv_track_sugerido": "private_cv",
            "historial_postulaciones_cruzado": True,
        }, {
            "id": "unsafe",
            "source_url": "javascript:alert(1)",
        }],
    }
    output = public_snapshot(source)
    result = json.dumps(output)
    assert len(output["atlas"]) == 1
    assert output["atlas"][0]["id"] == "job-1"
    assert output["atlas"][0]["search_lane"] == "REVIEW"
    assert "private@example.test" not in result
    assert "SUPERSECRET" not in result
    assert "private_notes" not in result
    assert "historial_postulaciones_cruzado" not in result
    assert "private_cv" not in result


def test_bad_schema_and_duplicate_rows_are_safe():
    output = public_snapshot({"atlas": [
        {"id": "one", "source_url": "https://jobs.example.com/1"},
        {"id": "one", "source_url": "https://jobs.example.com/2"},
        {"id": "two", "source_url": "http://jobs.example.com/2"},
    ], "sources": []})
    assert len(output["atlas"]) == 1
    assert output["sources"] == {}


def test_agtech_industry_is_separate_from_job_specialty():
    jobs = [{"id": "agzen:job1", "company": "AgZen", "source": "ashby",
             "title": "Software Engineering Co-op", "track": "software_ai",
             "source_url": "https://jobs.ashbyhq.com/agzen/job1"},
            {"id": "fake:job2", "company": "AgZen", "source": "unknown",
             "title": "Software Engineering Co-op", "track": "software_ai",
             "source_url": "https://example.com/jobs/2"}]
    records = public_snapshot({"atlas": jobs})["atlas"]
    assert records[0]["company_industry"] == "agtech"
    assert records[0]["track"] == "software_ai"
    assert "company_industry" not in records[1]
