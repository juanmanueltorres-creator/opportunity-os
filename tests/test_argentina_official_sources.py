from datetime import datetime, timezone
import httpx
import pytest

from app.radar.argentina_official_sources import (
    OFFICIAL_PAGES, parse_official_page, collect_argentina_official_pages,
)

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def page(title, location="Oficina en Catalinas, Retiro (CABA)", apply="POSTULATE"):
    return f"""<html><head><script>private()</script></head><body>
    <h1>{title}</h1><p>Estamos buscando un perfil que maneje Python, bases de
    datos, ArcGIS, documentación y sistemas geoespaciales.</p>
    <p>{location}</p><p>{apply}</p></body></html>"""


def test_official_geoai_source_requires_actual_source_heading_and_apply():
    vacancy = parse_official_page(page("Analista GeoAI"), "aeroterra-geoai", now=NOW)
    assert vacancy is not None
    assert vacancy.company == "Aeroterra"
    assert vacancy.location == "CABA, Argentina"
    assert vacancy.published_at is None
    assert vacancy.remote_policy is None
    assert "private()" not in vacancy.description
    assert vacancy.id == "publicpage:aeroterra-geoai"
    assert parse_official_page(page("Empresa cerró la búsqueda"),
        "aeroterra-geoai", now=NOW) is None
    assert parse_official_page(page("Analista GeoAI", apply="Información general"),
        "aeroterra-geoai", now=NOW) is None
    assert parse_official_page(page("Analista GeoAI", location="Sin ubicación"),
        "aeroterra-geoai", now=NOW) is None


def test_university_is_not_evidence_of_cordoba_location():
    html = page("Analista de Performance – Business Intelligence",
        "AMMAZY Argentina. Modalidad de trabajo 100% presencial. Publicado el 5 de octubre, 2026",
        "Para postularte, enviar CV")
    vacancy = parse_official_page(html, "utn-ammazy-bi", now=NOW)
    assert vacancy is not None
    assert vacancy.location is None
    assert vacancy.remote_policy == "onsite"
    assert vacancy.published_at == datetime(2026, 10, 5, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_live_collector_fail_closed_and_keeps_diagnostics_per_page():
    async def handler(request):
        if request.url.path.endswith("/geo-ai"):
            return httpx.Response(200, text=page("Analista GeoAI"),
                                  headers={"content-type": "text/html"})
        if request.url.path.endswith("/analista-funcional-gis"):
            return httpx.Response(200, text=page("Vacante removida"),
                                  headers={"content-type": "text/html"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        found, diagnostics = await collect_argentina_official_pages(client, now=NOW)
    assert [x.id for x in found] == ["publicpage:aeroterra-geoai"]
    assert diagnostics["publicpage:aeroterra-geoai"] == "OK (1 source page)"
    assert diagnostics["publicpage:aeroterra-funcional-gis"].startswith("NOT_CONFIRMED")
    assert diagnostics["publicpage:utn-ammazy-bi"].startswith("ERROR")
