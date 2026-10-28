"""Focused regressions for broader labor source coverage."""
import asyncio
from datetime import datetime, timezone
from app.models.domain import Opportunity
from app.radar.daily_search import classify, detect_listing_language
from app.radar import targeted_companies

NOW = datetime(2026, 10, 28, 15, tzinfo=timezone.utc)


def job(title: str, description: str = "Public employer listing", location="Remote") -> Opportunity:
    return Opportunity(
        id="test:1", source="ashby", source_id="1",
        source_url="https://jobs.ashbyhq.com/example/1",
        title=title, description=description, company="Employer",
        location=location, remote_policy="remote",
        discovered_at=NOW, published_at=NOW,
    )


def test_specialized_titles_are_not_all_development():
    expected = {
        "GIS Surveyor": "gis_geoscience",
        "Geotechnical Geologist": "gis_geoscience",
        "Agricultural Technology Specialist": "environment_agro",
        "Environmental Consultant": "environment_agro",
        "Product Designer": "design_web",
        "Cocinero": "income_operations",
        "Operario de depósito": "income_operations",
    }
    for title, track in expected.items():
        result = classify(job(title), include_worldwide_onsite=True)
        assert result is not None and result.track == track, title


def test_listing_language_is_separate_from_job_requirement():
    spanish = ("Buscamos experiencia para trabajar con nuestro equipo. "
               "La empresa ofrece desarrollo, tareas y responsabilidades. ") * 4
    english = ("We are looking for a candidate with experience and skills. "
               "Our team will work with the company on responsibilities. ") * 4
    assert detect_listing_language(spanish) == "ES"
    assert detect_listing_language(english) == "EN"
    assert detect_listing_language("QGIS Python") == "UNKNOWN"
    result = classify(job("GIS Analyst", spanish), include_worldwide_onsite=True)
    assert result is not None and result.listing_language == "ES"
    assert result.work_language == "UNKNOWN"
    assert result.as_public_dict()["listing_language"] == "ES"


def test_targeted_ats_is_bounded_and_fault_isolated(monkeypatch):
    class FakeAshby:
        def __init__(self, client, *, board_name, company_name, timeout_seconds):
            self.name = board_name
        async def fetch(self):
            if self.name == "klim":
                raise RuntimeError("test error")
            return [job("Agricultural Technology Specialist")]

    class FakeGreenhouse:
        def __init__(self, client, *, board_token, company_name, timeout_seconds):
            self.name = board_token
        async def fetch(self):
            return [job("GIS Surveyor")]

    monkeypatch.setattr(targeted_companies, "AshbyConnector", FakeAshby)
    monkeypatch.setattr(targeted_companies, "GreenhouseConnector", FakeGreenhouse)
    found, diagnostics = asyncio.run(targeted_companies.collect_targeted_companies(
        object(), now=NOW,
    ))
    assert diagnostics["ashby:klim"] == "ERROR:RuntimeError"
    assert diagnostics["greenhouse:ardentmc"].startswith("OK (")
    assert len(found) == len(targeted_companies.TARGET_BOARDS) - 1


def test_french_project_manager_does_not_become_restaurant_chef():
    result = classify(job("Freelance Chef de projet fonctionnel"), include_worldwide_onsite=True)
    assert result is None or result.track != "income_operations"
