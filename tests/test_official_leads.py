from datetime import datetime
from pathlib import Path
import json
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site" / "official-leads.js"
HTML = ROOT / "site" / "index.html"


def _lead_model(date):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    code = ("const m=require(process.argv[1]);"
            "console.log(JSON.stringify(m.officialLeadsForDate(new Date(process.argv[2]))))")
    proc = subprocess.run(
        [node, "-e", code, str(SRC), date],
        text=True, capture_output=True, check=True,
    )
    return json.loads(proc.stdout)


def test_verified_sources_have_direct_urls_and_explicit_review_boundaries():
    jobs = _lead_model("2026-10-29T12:00:00-03:00")
    assert len(jobs) == 5
    assert jobs[0]["company"].startswith("IDECOR")
    assert jobs[0]["apply_email"] == "idecor@cba.gov.ar"
    assert jobs[0]["apply_subject"] == "Gestor de Calidad de Datos Geoespaciales"
    assert jobs[1]["company"] == "ERM"
    assert jobs[1]["deadline"] == "2026-10-31"
    assert all(j["source_url"].startswith("https://") for j in jobs)
    assert all(j["reviewed_at"] == "2026-10-29" for j in jobs)
    assert all(j["check"] and j["requirements"] for j in jobs)
    assert "work_language" not in jobs[0]  # No inference from Spanish job text.


def test_expired_deadlines_and_old_observations_disappear_automatically():
    on_november = _lead_model("2026-11-01T12:00:00-03:00")
    assert all(j["id"] != "erm-r00032104" for j in on_november)
    assert _lead_model("2026-11-20T12:00:00-03:00") == []


def test_frontend_exposes_official_postings_and_copy_for_cv():
    html = HTML.read_text(encoding="utf-8")
    assert 'src="./official-leads.js"' in html
    assert 'id="officialLeads"' in html
    assert "renderOfficialLeads();" in html
    assert "Copiar requisitos para preparar CV" in html
    assert "Abrir correo para enviar CV" in html
    assert "mailto:" in html
    assert "No están confirmados como abiertos" in html
