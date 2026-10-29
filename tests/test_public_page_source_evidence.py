from datetime import datetime, timezone
from app.models.domain import Opportunity
from app.radar.source_evidence import source_evidence
from scripts.publish_public_snapshot import public_snapshot


def test_public_source_provenance_only_for_exact_curated_url():
    now = datetime(2026,10,29,tzinfo=timezone.utc)
    def job(url):
        return Opportunity(
            id="publicpage:aeroterra-geoai", source="publicpage",
            source_id="aeroterra-geoai", company="Aeroterra", title="Analista GeoAI",
            source_url=url, location="CABA, Argentina", description="Python y ArcGIS",
            discovered_at=now,
        )
    official = "https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales/geo-ai"
    evidence = source_evidence(job(official))
    assert evidence["source_check"] == "LISTED_ON_OFFICIAL_SOURCE"
    row = {"id":"publicpage:aeroterra-geoai", "source":"publicpage",
           "source_url":official, "company":"Aeroterra", "title":"Analista GeoAI",
           "description":"Python GIS", **evidence}
    record = public_snapshot({"generated_at":now.isoformat(), "atlas":[row]})["atlas"][0]
    assert record["source_check"] == "LISTED_ON_OFFICIAL_SOURCE"
    assert record["description"] == "Python GIS"
    bad = source_evidence(job("https://www.aeroterra.com/es-ar/trabaja-con-nosotros/fake"))
    assert bad["source_check"] == "NOT_CHECKED"
