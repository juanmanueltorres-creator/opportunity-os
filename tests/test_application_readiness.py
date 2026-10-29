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
