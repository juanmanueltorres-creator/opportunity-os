from __future__ import annotations

import hashlib

from app.operator_bridge.models import OperatorObservation, observation_sha256
from app.relationships.models import RelationshipEvent, RelationshipEventKind

_KIND_MAP: dict[str, RelationshipEventKind] = {
    "CONTACT_VERIFIED": "CONTACT_VERIFIED",
    "MESSAGE_SENT": "CONTACTED",
    "REPLY_RECEIVED": "REPLIED",
    "PROCESS_OPENED": "PROCESS_OPENED",
    "PROCESS_UPDATED": "PROCESS_UPDATED",
    "PROCESS_CLOSED": "PROCESS_CLOSED",
}
_PROCESS_KINDS = {"PROCESS_OPENED", "PROCESS_UPDATED", "PROCESS_CLOSED"}


def relationship_event_id(observation: OperatorObservation) -> str:
    identity = (
        f"{observation.source_type}|{observation.source_name}|"
        f"{observation.observation_id}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"opobs-{digest}"


def normalize_observation(observation: OperatorObservation) -> RelationshipEvent:
    if observation.kind == "CONTACT_VERIFIED" and observation.contact_id is None:
        raise ValueError("CONTACT_VERIFIED requires contact_id")

    metadata = {
        "operator_source_type": observation.source_type,
        "operator_source_name": observation.source_name,
        "operator_observation_id": observation.observation_id,
        "operator_observation_sha256": observation_sha256(observation),
    }

    if observation.kind in _PROCESS_KINDS and observation.process_label is not None:
        metadata["process_label"] = observation.process_label

    if observation.kind == "MESSAGE_SENT" and observation.contact_id is None:
        metadata["official_channel"] = "operator_observation"

    return RelationshipEvent(
        event_id=relationship_event_id(observation),
        account_id=observation.account_id,
        contact_id=observation.contact_id,
        kind=_KIND_MAP[observation.kind],
        occurred_at=observation.observed_at,
        reason=observation.reason,
        source_ref=observation.source_ref,
        metadata=metadata,
    )
