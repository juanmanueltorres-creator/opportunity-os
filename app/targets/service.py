import hashlib
import json
from datetime import datetime

from app.models.domain import CandidateProfile
from app.targets.models import TargetAccount, TargetAccountBatch, TargetAccountPolicy
from app.targets.scoring import assess_target_account
from app.targets.selector import OutreachHistory, select_target_batch


class EmptyOutreachHistory:
    def last_contacted_at(self, account_id: str) -> datetime | None:
        return None


def profile_fingerprint(profile: CandidateProfile) -> str:
    payload = profile.model_dump(mode="json", exclude_none=True)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TargetRadarService:
    def __init__(
        self,
        *,
        targets: list[TargetAccount],
        history: OutreachHistory | None = None,
        policy: TargetAccountPolicy | None = None,
    ) -> None:
        self._targets = list(targets)
        self._history = history or EmptyOutreachHistory()
        self._policy = policy or TargetAccountPolicy()

    def run(self, profile: CandidateProfile, *, now: datetime) -> TargetAccountBatch:
        assessments = [
            assess_target_account(account, profile, now=now)
            for account in self._targets
        ]
        return select_target_batch(
            assessments,
            self._policy,
            self._history,
            now=now,
            profile_fingerprint=profile_fingerprint(profile),
        )
