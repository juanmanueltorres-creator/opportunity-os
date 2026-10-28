"""Public static report: no private records, safe links, and global lane separation."""
from pathlib import Path

from app.radar.html_report import render_job_report


def test_render_html_filters_and_escapes(tmp_path: Path):
    out = tmp_path / "jobs.html"
    report = {
        "generated_at": "2026-10-27T12:00:00Z",
        "matches": [{
            "company": "<script>alert('x')</script>", "title": "GIS Jr",
            "source_url": "https://example.com/job/123",
            "location": "Córdoba", "track": "gis_geoscience",
            "score": 72, "source": "official",
        }],
        "needs_review": [{
            "company": "Unknown", "title": "Remote Python",
            "source_url": "javascript:alert(1)",
            "location": "Worldwide",
        }],
        "global_watchlist": [{
            "company": "European Startup", "title": "Backend Python",
            "source_url": "https://example.com/eu/role",
            "location": "Berlin", "track": "software_ai",
            "score": 55, "source": "ashby",
        }],
    }
    render_job_report(report, out)
    html = out.read_text(encoding="utf-8")
    assert "Atlas global" in html
    assert "GIS Jr" in html and "European Startup" in html
    assert "<script>alert(" not in html
    assert "&lt;script&gt;" in html
    assert "javascript:alert(1)" not in html
    assert "https://example.com/eu/role" in html
    assert "Gemini" in html
    assert "Historial" not in html
