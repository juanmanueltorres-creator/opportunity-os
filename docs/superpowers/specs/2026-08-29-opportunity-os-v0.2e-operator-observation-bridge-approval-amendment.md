# Opportunity OS V0.2E — Approval and Idempotent Retry Amendment

Date: 2026-08-29
Status: approved
Applies to: `2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md`

The V0.2E Operator Observation Bridge design is approved for implementation.

This amendment is normative where it clarifies the proposed design.

## Idempotent import retry precedence

An exact retry of an observation that has already been imported must return `ALREADY_IMPORTED` without another write, even when the relationship projection has changed as a consequence of the first successful import.

Import evaluation order is therefore:

1. normalize the submitted `OperatorObservation` deterministically;
2. derive its deterministic `RelationshipEvent` identity;
3. look up an existing event with that `event_id`;
4. if the existing event is semantically identical, return `ALREADY_IMPORTED` immediately with the stable deterministic receipt identity and perform no write;
5. if the existing event differs, return `CONFLICT` / `observation_identity_conflict`;
6. otherwise recompute the current preview from current relationship state;
7. compare the recomputed `preview_sha256` with the submitted preview hash;
8. if the hash differs, return `BLOCKED_STALE_PREVIEW`;
9. if the preview is domain-blocked, return `BLOCKED_DOMAIN`;
10. otherwise record the event through `RelationshipService.record()` and return `IMPORTED`.

This ordering preserves both guarantees:

- retries of the same accepted fact are idempotent;
- a not-yet-imported observation cannot use a stale confirmation after relevant relationship state changes.

No external action authority is introduced by this amendment.