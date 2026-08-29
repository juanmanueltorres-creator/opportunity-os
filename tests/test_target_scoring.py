from datetime import datetime, timedelta, timezone

from app.models.domain import CandidateProfile, CandidateTrack
from app.targets.models import TargetAccount, TargetSignal
from app.targets.scoring import assess_target_account, contactability_score, proximity_score

NOW = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)


def signal(label: str, value: float, *, age_days: int = 1) -> TargetSignal:
    return TargetSignal(
        label=label,
        value=value,
        source_url="https://example.com/source",
        observed_at=NOW - timedelta(days=age_days),
    )


def account(**overrides) -> TargetAccount:
    payload = dict(
        id="example",
        name="Example Corp",
        sectors=["technology"],
        role_families=["software engineer"],
        capability_tags=["python", "fastapi"],
        proximity_bucket="REMOTE",
        scale_stability_signal=signal("scale", 80),
        innovation_signal=signal("innovation", 90),
        contactability="GENERAL_CV",
        hiring_signal=signal("hiring", 50),
    )
    payload.update(overrides)
    return TargetAccount(**payload)


def test_proximity_mapping_is_explicit() -> None:
    assert proximity_score("VERY_CLOSE") == 100
    assert proximity_score("CLOSE") == 85
    assert proximity_score("CITY_WIDE") == 65
    assert proximity_score("LONG_COMMUTE") == 30
    assert proximity_score("REMOTE") == 100
    assert proximity_score("UNKNOWN") == 50


def test_contactability_mapping_is_explicit() -> None:
    assert contactability_score("APPLICATION_EMAIL") == 100
    assert contactability_score("VERIFIED_RECRUITER") == 90
    assert contactability_score("GENERAL_CV") == 85
    assert contactability_score("CAREERS_FORM") == 60
    assert contactability_score("UNKNOWN") == 50
    assert contactability_score("NONE") == 20


def test_best_track_is_selected_without_cross_track_merging() -> None:
    profile = CandidateProfile(
        name="Candidate",
        skills=["placeholder"],
        tracks=[
            CandidateTrack(
                id="hospitality",
                label="Hospitality",
                intents=["INCOME_NOW"],
                roles=["operations coordinator"],
                skills=["inventory"],
                domains=["hospitality"],
            ),
            CandidateTrack(
                id="tech",
                label="Tech",
                intents=["CAREER"],
                roles=["software engineer"],
                skills=["python", "fastapi"],
                domains=["technology"],
            ),
        ],
    )
    result = assess_target_account(account(), profile, now=NOW)
    assert result.best_track_id == "tech"
    assert result.capability_sector_fit == 100


def test_total_affinity_uses_declared_weights() -> None:
    profile = CandidateProfile(
        name="Candidate",
        skills=["python", "fastapi"],
        roles=["software engineer"],
        domains=["technology"],
    )
    result = assess_target_account(account(), profile, now=NOW)
    expected = round(0.30 * 100 + 0.20 * 100 + 0.15 * 80 + 0.15 * 90 + 0.10 * 85 + 0.10 * 50, 1)
    assert result.account_affinity == expected


def test_stale_provenance_lowers_confidence_and_surfaces_risk() -> None:
    stale = account(
        innovation_signal=signal("innovation", 90, age_days=400),
        hiring_signal=signal("hiring", 50, age_days=400),
    )
    profile = CandidateProfile(name="Candidate", skills=["python"], domains=["technology"])
    result = assess_target_account(stale, profile, now=NOW)
    assert result.confidence < 100
    assert any("stale" in risk.lower() for risk in result.risks)
