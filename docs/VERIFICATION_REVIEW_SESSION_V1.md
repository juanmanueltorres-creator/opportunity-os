# Verification Review Session V1

Verification Review Session turns the highest-priority items from Verification Queue
into a small, read-only batch of concrete review cards.

It is a work surface for humans, not an authority surface.

## Core boundary

```text
SESSION != VERIFICATION
SESSION != CONFIRMATION
SESSION != SEND
SESSION != CANDIDATE_FIT
```

A session does not write availability observations and does not expose a confirm action.

## Endpoint

`POST /api/v1/availability/verification/session`

Default batch size is 5. V1 allows 1..20 cards.

The session reuses Verification Queue ordering. It does not maintain a second ranking
system.

## Card contents

Each review card contains:

- rank;
- opportunity ID;
- title and company;
- review URL;
- source key/category;
- availability state;
- last seen / last verified timestamps;
- priority and queue reason codes;
- suggested action;
- deterministic review checklist;
- acceptable evidence kinds;
- explicit application deadline when known;
- the verification preview endpoint.

The card does not contain:

- a verification decision;
- a confirmer;
- a confirmation timestamp;
- a confirm endpoint;
- external actions.

## Review checklists

V1 uses bounded checklist codes.

For discovery-only signals:

- `LOCATE_OFFICIAL_SOURCE`
- `MATCH_ROLE_IDENTITY`
- `CONFIRM_APPLICATION_ACTIONABLE`
- `CAPTURE_EVIDENCE_URL`

For current-source verification:

- `CONFIRM_LISTING_LOADS`
- `MATCH_ROLE_IDENTITY`
- `CONFIRM_APPLICATION_ACTIONABLE`
- `CAPTURE_EVIDENCE_URL`

For re-verification:

- `CONFIRM_LISTING_LOADS`
- `MATCH_ROLE_IDENTITY`
- `CONFIRM_STILL_OPEN`
- `CONFIRM_APPLICATION_ACTIONABLE`
- `CAPTURE_EVIDENCE_URL`

When an explicit deadline exists, `CONFIRM_DEADLINE` is inserted before evidence
capture.

## Evidence guidance

Cards expose acceptable evidence kinds, not pre-filled evidence claims.

Discovery-only items accept only:

- `OFFICIAL_COMPANY_PAGE`
- `DIRECT_ATS`

Fast-market marketplace items may use:

- `DIRECT_PLATFORM`
- `MANUAL_REVIEW`

Other job boards allow official/ATS/platform/manual review evidence depending on what
the human reviewer actually finds.

The reviewer must still construct the verification evidence and run the separate
preview-confirm workflow.

## Session identity

A session ID hashes:

- session version;
- generated time;
- session/queue policy;
- ordered review cards;
- review URL;
- source identity/category;
- availability state;
- last seen timestamp;
- last verified timestamp;
- reason codes and suggested action.

It represents a review snapshot only. It is not persisted as workflow state.

If source or availability evidence changes, rebuilding the session produces a new
snapshot ID.

## Read-only behavior

Building a session does not:

- record `SEEN`;
- record `VERIFIED_OPEN`;
- record `VERIFIED_CLOSED`;
- fetch source URLs;
- mutate `Opportunity.status`;
- invoke verification confirm;
- publish Community Digest;
- send messages;
- use personal candidate scoring.

## Dependency boundary

The default Review Session is built on the same `VerificationQueueService` exposed by
Opportunity OS.

If the default queue is disabled, the default review session is unavailable rather than
constructing a second queue with different rules.

The explicit verification write workflow may remain disabled while review sessions are
still available.
