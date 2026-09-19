# Review Evidence Draft V1

Review Evidence Draft bridges a human Review Session card to the explicit Availability
Verification preview workflow.

It removes repetitive data-shaping work without granting write authority.

## Core boundary

```text
REVIEW CARD -> HUMAN FINDING -> DRAFT -> VERIFICATION PREVIEW
DRAFT != CONFIRM
DRAFT != WRITE
DRAFT != DECIDE
```

The human reviewer must explicitly provide the decision: `OPEN` or `CLOSED`.

The system never derives that decision from the review card, source type, HTTP status,
or queue reason.

## Endpoint

`POST /api/v1/availability/verification/draft`

The endpoint is read-only and is available independently from the opt-in verification
write surface.

The explicit confirm endpoint can remain disabled while evidence drafts are created.

## Input

A draft request contains:

- the exact `VerificationReviewCard`;
- explicit human decision;
- evidence observation time;
- evidence kind;
- evidence source identifier;
- HTTP/HTTPS evidence URL;
- optional note.

## Card integrity

Review cards carry a deterministic `card_sha256`.

The draft recomputes the hash from the card contents and rejects modified cards.

The hash binds:

- opportunity ID;
- review URL;
- source identity/category;
- availability state;
- last seen / last verified;
- deadline;
- priority/reasons/action;
- checklist;
- acceptable evidence kinds.

## Stale-card protection

Before creating evidence, the service compares the card's temporal availability snapshot
with current Availability Memory.

A change in:

- availability state;
- `last_seen_at`;
- `last_verified_at`

blocks the draft with `BLOCKED_STALE_CARD`.

The reviewer should rebuild the Review Session before continuing.

## Evidence-kind boundary

The evidence kind must be one of the kinds allowed by the review card.

Examples:

- discovery-only signal: official company page or direct ATS;
- fast-market marketplace: direct platform or manual review.

A Reddit discovery signal cannot be promoted into verification merely by choosing
`DIRECT_PLATFORM`.

## Output

A ready draft contains:

- stable draft ID;
- normalized `VerificationEvidence`;
- read-only `VerificationPreview`;
- no external actions.

The preview is produced by the existing verification workflow, so its hash is already
bound to the current Opportunity and Availability snapshots.

## Temporal integrity

Evidence `observed_at` must not be in the future relative to draft processing time.

The later confirmation workflow performs its own independent time and stale-preview
checks.

## Persistence

V1 does not persist drafts.

Rebuilding the same card + evidence against the same verification preview produces the
same draft ID.

If the underlying preview changes, the draft identity changes.

## Authority boundary

Review Evidence Draft V1 does not:

- fetch evidence URLs;
- inspect page content;
- infer OPEN/CLOSED;
- record availability observations;
- invoke confirm;
- mutate `Opportunity.status`;
- send messages;
- publish Community Digest;
- apply to opportunities.

The final write remains the explicit human confirmation workflow from Availability
Verification V1.
