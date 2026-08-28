from datetime import datetime, timedelta, timezone
from importlib import import_module

from app.models.domain import CandidateProfile, EvidenceItem, Opportunity

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)


def _scorer():
    return import_module("app.matching.scorer")


def _opportunity(*, required: list[str] | None = None, preferred: list[str] | None = None, description: str = "GIS work", location: str | None = None, remote_policy: str | None = None, published_at: datetime | None = None) -> Opportunity:
    return Opportunity(id="job-1", source="example", source_id="1", source_url="https://example.com/jobs/1", company="Example Co", title="GIS Developer", description=description, discovered_at=NOW, required_skills=required or [], preferred_skills=preferred or [], location=location, remote_policy=remote_policy, published_at=published_at)


def _profile(*, skills: list[str], domains: list[str] | None = None, locations: list[str] | None = None, remote_preferences: list[str] | None = None, evidence: list[EvidenceItem] | None = None) -> CandidateProfile:
    return CandidateProfile(name="Example Candidate", roles=["GIS Developer"], skills=skills, domains=domains or ["gis"], locations=locations or [], remote_preferences=remote_preferences or [], evidence=evidence or [])


def test_missing_required_skill_is_a_gap() -> None:
    assessment = _scorer().assess_opportunity(_opportunity(required=["python", "kubernetes"]), _profile(skills=["python"]), now=NOW)
    assert "kubernetes" in assessment.gaps
    assert assessment.mandatory_fit == 50.0
    assert assessment.strengths == ["python"]


def test_evidence_is_selected_only_when_verified_and_relevant() -> None:
    profile = _profile(skills=["postgis"], evidence=[EvidenceItem(label="GIS project", type="project", skills=["postgis"], domains=["gis"], verified=True), EvidenceItem(label="Unverified project", type="project", skills=["postgis"], domains=["gis"], verified=False), EvidenceItem(label="Unrelated project", type="project", skills=["excel"], domains=["finance"], verified=True)])
    assessment = _scorer().assess_opportunity(_opportunity(required=["postgis"]), profile, now=NOW)
    assert [item.label for item in assessment.evidence] == ["GIS project"]
    assert assessment.evidence_fit == 100.0


def test_matcher_does_not_infer_unlisted_skill_equivalence() -> None:
    assessment = _scorer().assess_opportunity(_opportunity(required=["postgis"]), _profile(skills=["postgresql"]), now=NOW)
    assert assessment.mandatory_fit == 0.0
    assert assessment.strengths == []
    assert assessment.gaps == ["postgis"]


def test_same_inputs_and_now_produce_identical_assessments() -> None:
    opportunity = _opportunity(required=["python"], description="Python GIS role", remote_policy="remote", published_at=NOW - timedelta(days=3))
    profile = _profile(skills=["python"], domains=["gis"], remote_preferences=["remote"])
    first = _scorer().assess_opportunity(opportunity, profile, now=NOW)
    second = _scorer().assess_opportunity(opportunity, profile, now=NOW)
    assert first == second


def test_explicit_location_conflict_adds_risk_and_caps_recommendation() -> None:
    evidence = EvidenceItem(label="Python GIS project", type="project", skills=["python"], domains=["gis"], verified=True)
    assessment = _scorer().assess_opportunity(_opportunity(required=["python"], description="Python GIS role", location="Madrid, Spain", remote_policy="on-site", published_at=NOW - timedelta(days=1)), _profile(skills=["python"], domains=["gis"], locations=["Argentina"], remote_preferences=["remote"], evidence=[evidence]), now=NOW)
    assert assessment.location_fit == 0.0
    assert "location conflict" in assessment.risks
    assert assessment.overall_score >= 75.0
    assert assessment.recommendation == "stretch"


def test_freshness_buckets_are_explicit() -> None:
    scorer = _scorer()
    profile = _profile(skills=["python"])
    assert scorer.assess_opportunity(_opportunity(required=["python"], published_at=NOW - timedelta(days=7)), profile, now=NOW).freshness_fit == 100.0
    assert scorer.assess_opportunity(_opportunity(required=["python"], published_at=NOW - timedelta(days=30)), profile, now=NOW).freshness_fit == 75.0
    assert scorer.assess_opportunity(_opportunity(required=["python"], published_at=NOW - timedelta(days=60)), profile, now=NOW).freshness_fit == 25.0
    assert scorer.assess_opportunity(_opportunity(required=["python"], published_at=NOW - timedelta(days=91)), profile, now=NOW).freshness_fit == 0.0


def test_v01_complete_assessment_contract_is_frozen() -> None:
    evidence = EvidenceItem(
        label="Python GIS project",
        type="project",
        skills=["python"],
        domains=["gis"],
        url="https://example.com/evidence/python-gis",
        verified=True,
    )
    opportunity = _opportunity(
        required=["python", "kubernetes"],
        preferred=["docker"],
        description="Python GIS platform engineering",
        location="Córdoba, Argentina",
        remote_policy="remote",
        published_at=NOW - timedelta(days=10),
    )
    profile = _profile(
        skills=["python", "sql"],
        domains=["gis"],
        locations=["Córdoba, Argentina"],
        remote_preferences=["remote"],
        evidence=[evidence],
    )

    assessment = _scorer().assess_opportunity(opportunity, profile, now=NOW)

    assert assessment.model_dump() == {
        "opportunity_id": "job-1",
        "overall_score": 67.5,
        "mandatory_fit": 50.0,
        "domain_fit": 100.0,
        "evidence_fit": 50.0,
        "location_fit": 100.0,
        "freshness_fit": 75.0,
        "strengths": ["python"],
        "gaps": ["kubernetes"],
        "risks": [],
        "evidence": [
            {
                "label": "Python GIS project",
                "type": "project",
                "skills": ["python"],
                "domains": ["gis"],
                "url": "https://example.com/evidence/python-gis",
                "verified": True,
            }
        ],
        "recommendation": "stretch",
        "explanation": (
            "mandatory=50.0; domain=100.0; evidence=50.0; location=100.0; "
            "freshness=75.0; matched=['python']; gaps=['kubernetes']; risks=[]"
        ),
    }
