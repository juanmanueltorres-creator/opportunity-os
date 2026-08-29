# Opportunity OS V0.2D — Implementation Plan Self-Review Corrections

This file is normative for execution and supersedes any conflicting wording in:

`docs/superpowers/plans/2026-08-29-opportunity-os-v0.2d-relationship-memory-context-bridge.md`

It also incorporates:

`docs/superpowers/specs/2026-08-29-opportunity-os-v0.2d-dormant-state-amendment.md`

## 1. Task 1 type correction

Use separate persisted and redacted state types:

```python
StoredRelationshipState = Literal[
    "UNTOUCHED",
    "CONTACTED",
    "REPLIED",
    "PROCESS_OPEN",
    "PROCESS_CLOSED",
]

ContextRelationshipState = Literal[
    "UNTOUCHED",
    "CONTACTED",
    "REPLIED",
    "PROCESS_OPEN",
    "PROCESS_CLOSED",
    "DORMANT",
]
```

`RelationshipAccount.relationship_state` uses `StoredRelationshipState`.
`RelationshipContext.relationship_state` uses `ContextRelationshipState`.

Do not add a dormant event.

## 2. Task 2 repository interface correction

`SQLiteRelationshipRepository` must explicitly expose:

```python
append_event(value: RelationshipEvent) -> RelationshipEvent
```

Behavior:

- missing `event_id`: insert and return the event;
- same `event_id` + identical payload: return the stored event unchanged;
- same `event_id` + conflicting payload: raise `ValueError("relationship event_id conflict")`.

The transactional service path may use an internal transaction-aware variant, but public repository tests must exercise the behavior above.

## 3. Task 3 NOTE_RECORDED behavior

`NOTE_RECORDED` is append-only private history and changes no account/contact projection by itself.
It must never be repurposed to write `DORMANT` or another hidden state transition.

## 4. Task 4 exact Context Bridge precedence

Use this precedence exactly:

```text
open process
    -> WATCH

active cooldown
    -> WATCH

historical relationship + explicit current reason + follow_up_min_days satisfied
    -> FOLLOW_UP

only held/non-usable contacts exist
    -> WATCH

no usable contacts and no held contacts
    -> RESEARCH_CONTACT

otherwise
    -> PREPARE_SPECULATIVE
```

There must be no unreachable held-only branch.

## 5. Dormant derivation

Before choosing the action, derive the redacted context state.

Pseudo-code:

```python
historical = (
    account.last_contacted_at is not None
    or account.last_reply_at is not None
    or account.relationship_state == "PROCESS_CLOSED"
)

follow_up_ready = (
    historical
    and bool(current_reason)
    and follow_up_age_ok
    and not account.open_process
    and not cooldown_active
)

context_state = account.relationship_state
if (
    historical
    and not account.open_process
    and not cooldown_active
    and not follow_up_ready
):
    context_state = "DORMANT"
```

Exception: keep `PROCESS_CLOSED` visible when the process closed recently and the configured follow-up minimum age has not yet elapsed; derive `DORMANT` only after that minimum age window.

Context generation must not persist `DORMANT` or append an event.
Add a test that reloads the account after context generation and proves the stored state is unchanged.

## 6. Current reason is read input, not an automatic write

`RelationshipMemory.context_for(..., current_reason=...)` treats `current_reason` as current run context.
It must not silently persist it as `last_reason`.

Persisting a reason requires an explicit `RelationshipEvent` or service write path. This prevents a read-only Target Accounts run from mutating private relationship history.

## 7. Task 5 target integration rule

Relationship context may block or elevate the target recommendation, but `PREPARE_SPECULATIVE` from relationship memory is only a non-blocking signal.

Exact merge rule:

```python
if relationship_action in {"WATCH", "FOLLOW_UP", "RESEARCH_CONTACT"}:
    final_action = relationship_action
else:
    final_action = affinity_action(item, policy)
```

The selector must never define or return `SEND`.

## 8. Coverage added by this self-review

Execution must include these tests in addition to the base plan:

```text
test_dormant_is_derived_without_persisting_state
test_recent_process_closed_remains_process_closed_before_follow_up_min_days
test_current_reason_read_does_not_mutate_last_reason
test_held_only_contacts_watch_before_generic_research_contact
test_note_recorded_does_not_change_projection
```
