from datetime import datetime, timezone
from scripts.triage_public_feed import priority, shortlist, markdown

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def job(**kwargs):
    row = {
        "id": "getonboard:gis-1", "source": "getonboard",
        "company": "Ejemplo", "title": "Analista GIS Jr",
        "source_url": "https://www.getonbrd.com/jobs/gis-jr",
        "work_language": "UNKNOWN", "listing_language": "ES",
        "argentina_eligible": "UNKNOWN", "remote_mode": "REMOTE",
        "category": "REVISAR",
    }
    row.update(kwargs)
    return row


def test_no_fabricated_apply_now():
    text = markdown({"atlas": [job()]}, now=NOW)
    assert "No son vacantes confirmadas para postular" in text
    assert "idioma laboral" in text


def test_reject_senior_english_and_incompatible_or_unrelated_roles():
    for changes in (
        {"title": "Senior GIS"},
        {"id": "getonboard:senior-python", "title": "Python"},
        {"work_language": "EN"},
        {"argentina_eligible": "NO"},
        {"listing_language": "EN"},
        {"title": "Desarrollador Liferay"},
        {"category": "EXPLORAR"},
    ):
        assert priority(job(**changes), now=NOW) is None


def test_higher_evidence_and_junior_ranks_first_without_padding():
    a = job(id="getonboard:j", argentina_eligible="YES", work_language="ES")
    b = job(id="getonboard:n", title="Python Developer")
    rows = shortlist({"atlas": [b, a]}, now=NOW, limit=20)
    assert len(rows) == 2
    assert rows[0]["job"]["id"] == "getonboard:j"



def test_relevant_geoai_and_bi_titles_reach_the_human_review_report():
    geo = job(
        id="publicpage:aeroterra-geoai",
        company="Aeroterra",
        title="Analista GeoAI",
        source_url="https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales/geo-ai",
        track="gis_geoscience", location="CABA, Argentina",
        argentina_eligible="YES",
    )
    bi = job(
        id="publicpage:utn-ammazy-bi",
        company="AMMAZY",
        title="Analista de Performance – Business Intelligence",
        source_url="https://portalseu.frc.utn.edu.ar/oportunidades-laborales/analista-de-performance-business-intelligence/",
        track="software_ai", location=None, remote_mode="ONSITE",
    )
    results = shortlist({"atlas": [geo, bi]}, now=NOW)
    assert {x["job"]["title"] for x in results} == {
        "Analista GeoAI", "Analista de Performance – Business Intelligence"
    }
    report = markdown({"atlas": [geo, bi]}, now=NOW)
    assert "disponibilidad para trabajar en Buenos Aires" in report
    assert "ciudad del puesto presencial" in report
