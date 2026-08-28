from app.models.domain import CandidateProfile, CandidateTrack


def effective_tracks(profile: CandidateProfile) -> list[CandidateTrack]:
    if profile.tracks:
        return profile.tracks
    return [
        CandidateTrack(
            id="default",
            label="Default",
            intents=["CAREER", "INCOME_NOW"],
            roles=profile.roles,
            skills=profile.skills,
            domains=profile.domains,
            evidence=profile.evidence,
            accepted_work_modes=profile.remote_preferences,
            no_go_constraints=profile.no_go_constraints,
        )
    ]
