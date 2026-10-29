"""Employer-owned job board links and collection boundaries stay transparent."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "site/index.html"


def test_aeroterra_direct_region_careers_and_source_evidence_labels():
    site = HTML.read_text(encoding="utf-8")
    assert 'href="https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales"' in site
    assert 'value="LISTED_ON_OFFICIAL_SOURCE"' in site
    assert "algunas posiciones puntuales de Aeroterra se consultan también en el recolector" in site


def test_outdated_contacted_role_is_not_a_featured_manual_application():
    site = HTML.read_text(encoding="utf-8")
    selected = (ROOT / "site/official-leads.js").read_text(encoding="utf-8")
    assert 'href="https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales/geo-ai"' not in site
    assert 'id: "aeroterra-geoai"' not in selected
    # The public employer directory remains available and private Gmail details
    # are never stored or used in the public feed.
