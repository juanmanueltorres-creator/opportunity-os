"""Daily career radar: conservative role matching and provenance safeguards."""
from datetime import datetime, timezone, timedelta

from app.models.domain import Opportunity
from app.radar.daily_search import (
    parse_getonbrd, classify, rank, text_only, TRACKS,
)
from app.radar.daily_persistence import persist

NOW=datetime(2026,10,26,14,tzinfo=timezone.utc)


def job(title="Desarrollador Python",location="LATAM",remote_policy="remote",
        description="Se busca desarrollador Python.",published_at=NOW):
    return Opportunity(id="remotive:101",source="remotive",source_id="101",
      source_url="https://remotive.com/remote-jobs/software-dev/test-101",
      company="Example Co",title=title,description=description,
      discovered_at=NOW,published_at=published_at,
      location=location,remote_policy=remote_policy)


def test_latam_remote_fits_software_with_cv_track():
    item=classify(job())
    assert item is not None
    assert item.argentina_eligible=="YES"
    assert item.remote_mode=="REMOTE"
    assert item.work_language=="UNKNOWN"  # Spanish ad does not prove team language
    assert item.cv_track=="desarrollo_software_ia"
    public=item.as_public_dict()
    assert public['description'] == 'Se busca desarrollador Python.'
    assert public['last_verified_at'] == 'No verificado'
    assert public["cv_pdf_generado"] is False
    assert public["historial_postulaciones_cruzado"] is False
    assert public["verification_status"]=="PENDING"


def test_gis_job_has_geoscience_cv():
    item=classify(job(title="GIS Analyst / PostGIS",location="Argentina"))
    assert item is not None
    assert item.track=="gis_geoscience"
    assert item.cv_track=="gis_geociencias"


def test_management_job_has_management_cv():
    item=classify(job(title="Coordinador de operaciones",location="Córdoba",
                      remote_policy="onsite"))
    assert item is not None
    assert item.track=="management_operations"
    assert item.cv_track=="management_ia"


def test_restricted_country_excluded_and_worldwide_not_assumed():
    restricted=classify(job(location="US only"))
    assert restricted is not None and restricted.argentina_eligible=="NO"
    assert rank([job(location="US only")],now=NOW)==[]
    unknown=classify(job(location="Worldwide"))
    assert unknown is not None and unknown.argentina_eligible=="UNKNOWN"


def test_unrelated_and_outside_argentina_onsite_not_recommended():
    assert classify(job(title="Registered nurse")) is None
    assert classify(job(location="New York",remote_policy="onsite")) is None


def test_explicit_language_only():
    es=classify(job(description="Idioma de trabajo: español. Python"))
    assert es is not None and es.work_language=="ES"
    en=classify(job(description="Fluent English required for this Python role"))
    assert en is not None and en.work_language=="EN"
    unknown=classify(job(description="Postulación desarrollador Python en español"))
    assert unknown is not None and unknown.work_language=="UNKNOWN"


def test_old_roles_not_in_fresh_search():
    stale=job(published_at=NOW-timedelta(days=100))
    assert rank([stale],now=NOW)==[]


def test_getonbrd_parses_only_known_direct_job_urls():
    payload={"data":[
      {"id":"55","attributes":{"title":"Analista GIS","company_name":"Startup Demo",
        "description":"SIG remoto","location":"LatAm","remote":True,
        "published_at":"2026-10-25T10:00:00Z"},
       "links":{"public_url":"https://www.getonbrd.com/jobs/analista-gis"}},
      {"id":"56","attributes":{"title":"Developer","company_name":"No Link"},
       "links":{}},
      {"id":"57","attributes":{"title":"Backend","company_name":"Adversarial"},
       "links":{"public_url":"https://evil.example/phishing"}}
    ]}
    got=parse_getonbrd(payload,now=NOW)
    assert len(got)==1
    assert got[0].source=="getonboard"
    assert got[0].id=="getonboard:55"
    assert got[0].published_at==datetime(2026,10,25,10,tzinfo=timezone.utc)


def test_private_sync_missing_secret_never_accesses_database(monkeypatch):
    monkeypatch.delenv("OPPORTUNITY_POSTGRES_WRITE_DSN",raising=False)
    result=persist([classify(job())])
    assert result["status"]=="NOT_CONFIGURED"
    assert not result["history_checked"]


def test_html_is_not_evidence_of_team_language():
    assert text_only("<p>Python &amp; QGIS</p>")=="Python & QGIS"


def test_getonbrd_official_epoch_and_company_expand():
    published=1792936800
    payload={"data":[{
      "id":"remote-55",
      "attributes":{
        "title":"Desarrollador fullstack",
        "description":"Desarrollo de servicios y API",
        "remote":True,"remote_modality":"fully_remote",
        "remote_zone":"Latin America",
        "countries":["Argentina","Chile"],
        "published_at":published,
        "company":{"data":{"id":"company-10","type":"company"}}
      },
      "links":{"public_url":"https://www.getonbrd.com/jobs/fullstack-remoto"}
    }],
    "included":[{"type":"company","id":"company-10",
                 "attributes":{"name":"Startup LATAM"}}]}
    out=parse_getonbrd(payload,now=NOW)
    assert len(out)==1
    assert out[0].company=="Startup LATAM"
    assert out[0].location=="Latin America"
    assert out[0].published_at==datetime.fromtimestamp(published,tz=timezone.utc)
    assert classify(out[0]).argentina_eligible=="YES"


def test_explicit_foreign_country_restrictions_never_rank_for_argentina():
    from app.radar.daily_search import _restricted_location
    for country in ("India", "Philippines", "United States",
                    "Canada, Israel, UK", "Poland, United States",
                    "USA", "Sweden, UK", "Europe", "Hungary"):
        assert _restricted_location(country)
        candidate=classify(job(location=country))
        assert candidate is not None and candidate.argentina_eligible=="NO"
        assert rank([job(location=country)],now=NOW)==[]


def test_worldwide_and_latam_remain_unverified_or_evidenced():
    from app.radar.daily_search import _restricted_location
    assert not _restricted_location("Anywhere")
    assert not _restricted_location("Worldwide")
    assert not _restricted_location("Argentina, Chile")
    assert classify(job(location="Anywhere")).argentina_eligible=="UNKNOWN"
    assert classify(job(location="Argentina")).argentina_eligible=="YES"


def test_getonboard_remote_boost_does_not_claim_ar_eligibility():
    other=job(location="Remote")
    regional=other.model_copy(update={"id":"getonboard:2","source":"getonboard","source_id":"2"})
    a=classify(other)
    b=classify(regional)
    assert b is not None and a is not None
    assert b.score>a.score
    assert b.argentina_eligible=="UNKNOWN"


def test_duplicate_company_role_from_different_feeds_returns_one():
    original=job(title="Python Developer",location="LATAM")
    mirror=original.model_copy(update={
      "id":"jobicy:321","source":"jobicy","source_id":"321",
      "source_url":"https://jobicy.com/jobs/321"
    })
    assert len(rank([original,mirror],now=NOW))==1


def test_colombian_sena_training_program_excluded_from_general_radar():
    assert classify(job(title="Aprendiz de Inteligencia Artificial Contrato Sena")) is None
