"""No geography-only 'apply' claims and source details stay text-only."""
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "site/index.html"


def test_public_job_card_shows_requirements_and_uncertainty():
    html = HTML.read_text(encoding="utf-8")
    assert "CANDIDATA PARA POSTULAR" not in html
    assert "j.category==='POSTULAR AHORA'" in html
    assert "Requisitos y comprobaciones pendientes" in html
    assert "j.description" in html
    assert "j.readiness_reasons" in html
    assert "art.append(detail)" in html
