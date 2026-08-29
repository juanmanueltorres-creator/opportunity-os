import hashlib
import json
from datetime import datetime

from app.models.domain import CandidateProfile
from app.relationships.context import EmptyRelationshipMemory, RelationshipMemory
from app.targets.models import TargetAccount, TargetAccountBatch, TargetAccountPolicy
from app.targets.scoring import assess_target_account
from app.targets.selector import select_target_batch


def profile_fingerprint(profile: CandidateProfile) -> str:
    payload = profile.model_dump(mode="json", exclude_none=True)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TargetRadarService:
    def __init__(
        self,
        *,
        targets: list[TargetAccount],
        relationship_memory: RelationshipMemory | None = None,
        policy: TargetAccountPolicy | None = None,
    ) -> None:
        self._targets = list(targets)
        self._relationship_memory = relationship_memory or EmptyRelationshipMemory()
        self._policy = policy or TargetAccountPolicy()

    def run(
        self,
        profile: CandidateProfile,
        *,
        now: datetime,
        current_reasons: dict[str, str] | None = None,
    ) -> TargetAccountBatch:
        assessments = [
            assess_target_account(account, profile, now=now)
            for account in self._targets
        ]
        reasons = current_reasons or {}
        relationship_contexts = {
            item.account_id: self._relationship_memory.context_for(
                item.account_id,
                now=now,
                current_reason=reasons.get(item.account_id),
            )
            for item in assessments
        }
        return select_target_batch(
            assessments,
            self._policy,
            relationship_contexts,
            now=now,
            profile_fingerprint=profile_fingerprint(profile),
        )
