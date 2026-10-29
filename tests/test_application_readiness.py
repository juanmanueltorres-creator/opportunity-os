from datetime import datetime, timezone
from app.radar.application_readiness import application_readiness


def test_unknown_is_review():
    assert application_readiness({}, now=datetime.now(timezone.utc))["category"] == "REVISAR"


def test_senior_and_c1_override_score():
    for title, description in [("Senior Python", ""), ("Python", "Inglés C1 obligatorio")]:
        row = {"title": title, "description": description, "score": 100}
        assert application_readiness(row, now=datetime.now(timezone.utc))["category"] == "EXPLORAR"


def test_language_of_listing_is_not_work_language():
    row = {"listing_language": "ES", "title": "Analista junior"}
    assert application_readiness(row, now=datetime.now(timezone.utc))["category"] == "REVISAR"



def test_senior_colleagues_do_not_disqualify_junior_candidate():
    row = {"title": "Analista GIS Jr", "description": "Trabajará con profesionales senior y un mentor de tecnología."}
    assert application_readiness(row, now=datetime.now(timezone.utc))["category"] == "REVISAR"


def test_english_desirable_is_not_obligatory():
    row = {"title": "Analista Geoespacial", "description": "Inglés avanzado deseable pero no excluyente."}
    assert application_readiness(row, now=datetime.now(timezone.utc))["category"] == "REVISAR"


def test_explicit_english_requirement_and_work_language_block():
    for row in (
        {"title": "GIS Analyst", "description": "Fluent English required for calls."},
        {"title": "Python Jr", "work_language": "EN"},
        {"title": "Soporte", "description": "Inglés B2 obligatorio."}
    ):
        assert application_readiness(row, now=datetime.now(timezone.utc))["category"] == "EXPLORAR"



def test_required_experience_and_native_english_are_not_daily_priority():
    examples = [
        {"title": "Support Engineer",
         "description": "At least five years of hands-on experience in support engineering."},
        {"title": "Geospatial Engineer",
         "description": "Experiencia mínima de 4 años en geoespacial."},
        {"title": "GIS analyst",
         "description": "Experiencia: 3 a 5 años en puestos similares."},
        {"title": "Technical Support Engineer",
         "description": "Native or near-native English, comfortable leading calls with US customers."},
    ]
    for row in examples:
        result = application_readiness(row, now=datetime.now(timezone.utc))
        assert result["category"] == "EXPLORAR", row
        assert result["readiness_reasons"], row


def test_context_is_not_an_experience_requirement():
    for row in [
        {"title": "Analista GIS Jr", "description": "Trabajará con un mentor senior."},
        {"title": "Analista de Datos Junior", "description": "La empresa tiene más de cinco años de historia."},
        {"title": "GIS", "description": "Inglés nativo deseable, no excluyente."},
    ]:
        assert application_readiness(row, now=datetime.now(timezone.utc))["category"] == "REVISAR", row
