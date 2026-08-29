# Opportunity OS V0.2D — Dormant State Amendment

Date: 2026-08-29
Status: approved clarification
Applies to: `2026-08-29-opportunity-os-v0.2d-relationship-memory-context-bridge-design.md`

## Decision

`DORMANT` is a **derived Context Bridge state**, not a persisted `RelationshipAccount` state and not an event-driven transition.

This amendment resolves an ambiguity in the base design: the original event vocabulary had no legitimate event whose purpose was only to write `DORMANT`, and reads must not mutate state merely because time passed.

## Stored vs derived states

Persisted account states:

```text
UNTOUCHED
CONTACTED
REPLIED
PROCESS_OPEN
PROCESS_CLOSED
```

Redacted context states:

```text
UNTOUCHED
CONTACTED
REPLIED
PROCESS_OPEN
PROCESS_CLOSED
DORMANT
```

`RelationshipAccount.relationship_state` uses the persisted-state type.
`RelationshipContext.relationship_state` uses the broader context-state type.

## Dormant derivation

The Context Bridge may emit `DORMANT` when all are true:

1. historical relationship exists (`last_contacted_at` or `last_reply_at` is present, or stored state is `PROCESS_CLOSED`);
2. `open_process == false`;
3. no active cooldown exists;
4. there is no explicit current follow-up reason that passes the follow-up timing gate.

Deriving `DORMANT` does not write to SQLite and does not append an event.

A later `CONTACTED` or `PROCESS_OPENED` event updates the persisted account state normally; there is no `DORMANT` event to clear.

## Consequences

- No `RELATIONSHIP_DORMANT` event is added.
- `NOTE_RECORDED` remains a note event and must not be abused as a hidden state transition.
- The append-only audit trail remains semantically clean.
- Context generation stays side-effect free.
- Tests must prove that dormant derivation does not mutate the stored `RelationshipAccount`.
