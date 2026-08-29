# Opportunity OS V0.2D — Review Fixes Amendment

Date: 2026-08-29
Status: approved
Applies to: PR #9 / V0.2D Relationship Memory + Context Bridge

This amendment records the final review corrections applied before merge.

## 1. Explicit reconnect reasons

`FOLLOW_UP` must be reachable through the shipped operator path, not only through direct internal calls.

`TargetRadarService.run()` therefore accepts optional per-account `current_reasons` and forwards the matching reason into `RelationshipMemory.context_for(...)`.

`POST /api/v1/targets/radar/run` may receive:

```json
{
  "current_reasons": {
    "example-account": "new relevant role published"
  }
}
```

The single-account read-only relationship context endpoint may also receive `current_reason` as a query parameter.

Reasons are operator-provided input. They do not authorize drafts, sends, applications, enrichment or any other external mutation.

## 2. Recent closed processes remain visible

`DORMANT` remains a derived read-side state, but it is derived only after the relationship has reached `follow_up_min_days`.

A recently closed process therefore remains `PROCESS_CLOSED` during the minimum-age window instead of becoming immediately indistinguishable from an old dormant relationship.

## 3. Chronological event integrity

Relationship events are projected only in deterministic chronological order.

For each account, new events must advance the ordered key:

```text
(occurred_at, event_id)
```

An older/out-of-order event is rejected before insertion or projection. An identical replay of an already-stored `event_id` remains idempotent.

This keeps the current-state projection consistent with the append-only event history and prevents delayed observations from reopening or regressing newer state.

## 4. Contact registration clarification

The approved implementation plan defines `register_contact(contact)` as the private directory seed operation.

`CONTACT_VERIFIED` therefore requires an existing contact belonging to the same account and updates its verification state/observation time. It does not create a brand-new contact from event metadata in V0.2D.

Operator Integration may later add an authorized adapter that seeds contacts and records verification observations without changing this boundary.
