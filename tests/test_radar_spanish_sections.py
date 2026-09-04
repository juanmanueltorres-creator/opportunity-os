from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.radar.extractor import RuleBasedRequirementExtractor

NOW = datetime(2026, 9, 4, 18, 0, tzinfo=timezone.utc)


def _opportunity(description: str) -> Opportunity:
    return Opportunity(
        id="manual:aeroterra-section-regression",
        source="manual",
        source_id="aeroterra-section-regression",
        source_url="https://example.com/aeroterra/geoai",
        company="Aeroterra",
        title="Analista GeoAI",
        description=description,
        discovered_at=NOW,
    )


def test_spanish_requirement_sections_classify_bullets_by_heading() -> None:
    description = """Lo que buscamos:
- Python
- Bases de datos
Valoraremos:
- ArcGIS
- Experiencia en GIS
"""

    enrichment = RuleBasedRequirementExtractor().extract(_opportunity(description))

    actual = {
        (item.kind, item.value, item.importance, item.provenance.source_text)
        for item in enrichment.requirements
    }

    assert ("skill", "Python", "mandatory", "- Python") in actual
    assert ("skill", "Bases de datos", "mandatory", "- Bases de datos") in actual
    assert ("skill", "ArcGIS", "preferred", "- ArcGIS") in actual
    assert (
        "experience",
        "Experiencia en GIS",
        "preferred",
        "- Experiencia en GIS",
    ) in actual


def test_section_heading_support_bumps_extractor_version_for_cache_invalidation() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity("Lo que buscamos:\n- Python")
    )

    assert enrichment.extractor_version == "rules-v2"
