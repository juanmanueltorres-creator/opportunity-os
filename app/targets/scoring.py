from datetime import datetime, timezone

from app.models.domain import CandidateProfile, CandidateTrack
from app.radar.profile import effective_tracks
from app.targets.models import Contactability, ProximityBucket, TargetAccount, TargetAccountAssessment

_PROXIMITY_SCORES: dict[str, float] = {
    "VERY_CLOSE": 100,
    "CLOSE": 85,
    "CITY_WIDE": 65,
    "LONG_COMMUTE": 30,
    "REMOTE": 100,
    "UNKNOWN": 50,
}

_CONTACTABILITY_SCORES: dict[str, float] = {
    "APPLICATION_EMAIL": 100,
    "VERIFIED_RECRUITER": 90,
    "GENERAL_CV": 85,
    "CAREERS_FORM": 60,
    "UNKNOWN": 50,
    "NONE": 20,
}


def proximity_score(bucket: ProximityBucket) -> float:
    return _PROXIMITY_SCORES[bucket]


def contactability_score(value: Contactability) -> float:
    return _CONTACTABILITY_SCORES[value]


def _norm(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def _overlap_score(required: set[str], offered: set[str]) -> float:
    if not required:
        return 50.0
    if not offered:
        return 0.0
    return round(100 * len(required & offered) / len(required), 1)


def _track_fit(account: TargetAccount, track: CandidateTrack) -> float:
    role_score = _overlap_score(_norm(account.role_families), _norm(track.roles))
    account_capabilities = _norm(account.sectors + account.capability_tags)
    track_capabilities = _norm(track.domains + track.skills)
    capability_score = _overlap_score(account_capabilities, track_capabilities)
    return round(0.5 * role_score + 0.5 * capability_score, 1)


def _signal_freshness(observed_at: datetime, now: datetime) -> float:
    age_days = max(0, (now - observed_at).days)
    if age_days <= 90:
        return 100.0
    if age_days <= 180:
        return 75.0
    if age_days <= 365:
        return 60.0
    return 40.0


def assess_target_account(
    account: TargetAccount,
    profile: CandidateProfile,
    *,
    now: datetime,
) -> TargetAccountAssessment:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)

    tracks = effective_tracks(profile)
    ranked_tracks = sorted(
        ((_track_fit(account, track), track.id) for track in tracks),
        key=lambda item: (-item[0], item[1]),
    )
    capability_sector_fit, best_track_id = ranked_tracks[0] if ranked_tracks else (50.0, None)

    proximity_fit = proximity_score(account.proximity_bucket)
    contact_fit = contactability_score(account.contactability)
    scale = account.scale_stability_signal.value
    innovation = account.innovation_signal.value
    hiring = account.hiring_signal.value

    affinity = round(
        0.30 * capability_sector_fit
        + 0.20 * proximity_fit
        + 0.15 * scale
        + 0.15 * innovation
        + 0.10 * contact_fit
        + 0.10 * hiring,
        1,
    )

    signal_freshness = [
        _signal_freshness(account.scale_stability_signal.observed_at, now),
        _signal_freshness(account.innovation_signal.observed_at, now),
        _signal_freshness(account.hiring_signal.observed_at, now),
    ]
    confidence = round(sum(signal_freshness) / len(signal_freshness), 1)

    reasons: list[str] = []
    risks: list[str] = []
    if capability_sector_fit >= 75:
        reasons.append("Strong candidate-track and target capability overlap")
    if proximity_fit >= 85:
        reasons.append("Favorable proximity or remote-access signal")
    if account.contactability in {"APPLICATION_EMAIL", "VERIFIED_RECRUITER", "GENERAL_CV"}:
        reasons.append("Usable verified/public contact path")
    if any(value < 60 for value in signal_freshness):
        risks.append("One or more target signals are stale and should be refreshed")
    if account.contactability in {"NONE", "UNKNOWN"}:
        risks.append("No strong contact path is currently available")

    return TargetAccountAssessment(
        account_id=account.id,
        account_name=account.name,
        best_track_id=best_track_id,
        capability_sector_fit=capability_sector_fit,
        proximity_fit=proximity_fit,
        scale_stability=scale,
        innovation=innovation,
        contactability_fit=contact_fit,
        hiring_signal=hiring,
        account_affinity=affinity,
        confidence=confidence,
        reasons=reasons,
        risks=risks,
        cooldown_active=False,
        recommended_action="WATCH",
    )
