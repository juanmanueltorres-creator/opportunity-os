"""Official Argentina employer portals are visible without claiming API ingestion."""
from pathlib import Path


def test_ypf_is_official_and_labeled_manual_not_ingested():
    html = (Path(__file__).resolve().parents[1] / "site" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'https://oportunidades.ypf.com/search/' in html
    assert 'https://oportunidades.ypf.com/go/Negocios/9521900/' in html
    assert 'https://trabajomineria.salta.gob.ar/trabajos/' in html
    assert 'fuentes realmente ejecutadas' in html
    assert 'no fuentes ya integradas' in html
    assert '10 días corridos' in html
    assert 'trabajo-de-geologo-en-cordoba' not in html
    assert 'trabajo-de-geologia' in html
