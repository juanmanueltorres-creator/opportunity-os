"""Employer-owned Argentina career links are explicitly MANUAL, not collected."""
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "site/index.html"


def test_aeroterra_direct_regional_careers_are_official_manual_links():
    site = HTML.read_text(encoding="utf-8")
    assert 'href="https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales"' in site
    assert 'href="https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales/geo-ai"' in site
    assert "Todavía no se importan automáticamente desde estos sitios" in site
