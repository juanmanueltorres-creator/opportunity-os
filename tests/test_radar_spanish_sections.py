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


def test_aeroterra_sections_normalize_capabilities_without_promoting_soft_requirements() -> None:
    description = """Lo que buscamos
• Estudiantes avanzados o graduados de Sistemas, Ciencias de la Computación, Ciencia de Datos, Inteligencia Artificial o carreras afines.
• Conocimientos de Python y bases de datos.
• Interés por Machine Learning, Inteligencia Artificial y analítica de datos.
• Capacidad analítica, orientación a la resolución de problemas y vocación por el aprendizaje continuo.
• Buenas habilidades de comunicación para interactuar con usuarios y comprender necesidades de negocio.

Valoraremos
• Conocimientos de Computer Vision.
• Conocimientos o experiencia en la plataforma ArcGIS y tecnologías geoespaciales.
• Participación en proyectos vinculados a Sistemas de Información Geográfica (GIS), analítica espacial o GeoAI.
"""

    enrichment = RuleBasedRequirementExtractor().extract(_opportunity(description))

    mandatory_skills = {
        item.value
        for item in enrichment.requirements
        if item.importance == "mandatory" and item.kind == "skill"
    }
    preferred_skills = {
        item.value
        for item in enrichment.requirements
        if item.importance == "preferred" and item.kind == "skill"
    }
    education = [item for item in enrichment.requirements if item.kind == "education"]
    other = [item for item in enrichment.requirements if item.kind == "other"]
    experience = [item for item in enrichment.requirements if item.kind == "experience"]

    assert mandatory_skills == {"Python", "bases de datos"}
    assert {"Computer Vision", "ArcGIS", "tecnologías geoespaciales"} <= preferred_skills
    assert len(education) == 1
    assert any(item.value.startswith("Interés por Machine Learning") for item in other)
    assert any(item.value.startswith("Capacidad analítica") for item in other)
    assert any(item.value.startswith("Buenas habilidades de comunicación") for item in other)
    assert any(
        item.value.startswith("Participación en proyectos vinculados")
        for item in experience
    )


def test_spanish_section_normalization_bumps_extractor_version_for_cache_invalidation() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity("Lo que buscamos:\n- Conocimientos de Python y bases de datos")
    )

    assert enrichment.extractor_version == "rules-v3"
