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


def test_public_source_evidence_survives_but_private_notes_do_not():
    row = {
        "id": "getonboard:regional", "source": "getonboard",
        "company": "Empresa GIS", "title": "GIS Analyst LATAM",
        "source_url": "https://www.getonbrd.com/jobs/123",
        "argentina_eligible": "YES",
        "eligibility_evidence": "Cobertura geográfica declarada en el título: GIS Analyst LATAM",
        "work_language": "ES",
        "language_evidence": "Requisito explícito en la descripción",
        "private_notes": "Nunca exportar",
    }
    safe = public_snapshot({"atlas": [row]})["atlas"][0]
    assert safe["eligibility_evidence"].startswith("Cobertura geográfica declarada")
    assert safe["language_evidence"] == "Requisito explícito en la descripción"
    assert "private_notes" not in safe
    assert "Nunca exportar" not in json.dumps(safe, ensure_ascii=False)


def test_untrusted_evidence_is_not_forwarded():
    row = {
        "id": "ashby:unsafe", "source": "ashby",
        "company": "Empresa", "title": "Python", "source_url": "https://jobs.ashbyhq.com/x/y",
        "argentina_eligible": "YES",
        "eligibility_evidence": "Secret user profile: private@example.test",
        "work_language": "ES",
        "language_evidence": "private@example.test",
    }
    safe = public_snapshot({"atlas": [row]})["atlas"][0]
    assert safe["eligibility_evidence"] is None
    assert safe["language_evidence"] is None
    assert "private@example.test" not in json.dumps(safe)


def test_public_description_is_exported_only_from_provider_board():
    report = {"atlas": [{
        "id": "getonboard:gis", "source": "getonboard",
        "title": "Analista GIS", "source_url": "https://www.getonbrd.com/jobs/gis",
        "description": "<p>Python, QGIS y PostGIS</p>",
        "category": "REVISAR",
        "readiness_reasons": ["language_compatible_verified", "SECRET token"],
        "candidate_email": "secret@example.org"
    }]}
    job = public_snapshot(report)["atlas"][0]
    assert job["description"] == "Python, QGIS y PostGIS"
    assert job["category"] == "REVISAR"
    assert job["readiness_reasons"] == ["language_compatible_verified"]
    assert "secret@example.org" not in json.dumps(job)


def test_private_manual_description_and_unknown_checks_are_not_exported():
    job = public_snapshot({"atlas": [{
        "id": "manual:1", "source": "manual", "title": "GIS",
        "source_url": "https://example.com/1",
        "description": "CV privado: private@example.org",
        "readiness_reasons": ["private@example.org"],
    }]})["atlas"][0]
    assert job["description"] is None
    assert job["readiness_reasons"] == []
    assert job["category"] == "REVISAR"


def test_public_description_is_bounded():
    job = public_snapshot({"atlas": [{
        "id": "ashby:long", "source": "ashby", "title": "Python",
        "source_url": "https://jobs.ashbyhq.com/org/long",
        "description": "Python " * 1000
    }]})["atlas"][0]
    assert len(job["description"]) <= 2200
    assert job["description_truncated"] is True
