from importlib import import_module

from app.models.domain import CandidateProfile, CandidateTrack


def _radar_profile():
    return import_module("app.radar.profile")


def test_legacy_profile_becomes_one_default_track() -> None:
    profile = CandidateProfile(
        name="Example",
        roles=["GIS Developer"],
        skills=["python"],
        domains=["gis"],
        remote_preferences=["remote"],
    )

    tracks = _radar_profile().effective_tracks(profile)

    assert len(tracks) == 1
    assert tracks[0].id == "default"
    assert tracks[0].label == "Default"
    assert tracks[0].intents == ["CAREER", "INCOME_NOW"]
    assert tracks[0].roles == ["GIS Developer"]
    assert tracks[0].skills == ["python"]
    assert tracks[0].accepted_work_modes == ["remote"]


def test_explicit_income_track_does_not_inherit_root_tech_skills() -> None:
    gastronomy = CandidateTrack(
        id="gastronomy_operations",
        label="Gastronomy operations",
        intents=["INCOME_NOW"],
        roles=["Pizzero"],
        skills=["pizza", "stock"],
        domains=["gastronomy"],
    )
    profile = CandidateProfile(
        name="Example",
        roles=["GIS Developer"],
        skills=["python", "postgis"],
        domains=["gis"],
        tracks=[gastronomy],
    )

    tracks = _radar_profile().effective_tracks(profile)

    assert tracks == [gastronomy]
    assert "python" not in tracks[0].skills
    assert "postgis" not in tracks[0].skills
