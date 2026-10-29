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
