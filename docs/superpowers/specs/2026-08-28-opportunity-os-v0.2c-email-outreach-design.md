# Opportunity OS — V0.2C Email-first + Approval Design

Date: 2026-08-28
Status: review
Base: `main` at `2f3b0676c64eb6f7cb9831c57ff85258d5e2ced0` (V0.2A1 + V0.2B merged)
Parent roadmap: private Opportunity OS operational context in the knowledge vault

## Purpose

V0.2C turns a prepared `ApplicationPacket` into a safe, reviewable outreach workflow that can be operated from ChatGPT using connected Gmail and, only when necessary, Apollo or other authorized contact sources.

The goal is practical: a strong `HIGH` or `MEDIUM` radar opportunity should be able to move from a verified CV packet to a personalized Gmail draft with the correct attachment, then to an explicitly approved send, without inventing claims, guessing email addresses, duplicating sends, or embedding Gmail/Apollo credentials inside Opportunity OS.

V0.2C is designed to be usable incrementally. The first operational slice should support real applications quickly, while preserving enough typed state and hashing to harden the workflow over time.

## Product decisions already approved

1. Contact priority is:

```text
published vacancy email
→ official Careers / HR application email
→ verified recruiter / Talent Acquisition contact
→ manual/form channel
```

2. Opportunity OS may automatically prepare outreach artifacts for `HIGH` and `MEDIUM` selected opportunities. `STRETCH` opportunities require explicit manual promotion before outreach preparation.

3. Opportunity OS does not create Gmail drafts automatically. ChatGPT creates a draft only when the user asks for that external action.

4. Opportunity OS does not embed an LLM for email copy. It produces a structured `OutreachBrief`; ChatGPT writes the email from that brief plus the immutable application packet.

5. Apollo is optional fallback infrastructure, not a core dependency. Search may identify recruiter/TA candidates, but any enrichment that consumes credits requires the user's explicit credit confirmation before the external action.

6. Approval is bound to exact semantic content. A material change to recipient, subject, body, attachment identity/content, or thread/reply target invalidates approval.

7. Sending is always an explicit external action. V0.2C never treats preparation, draft creation, or user interest as authorization to send.

## Core principles

1. **Prepare automatically; act externally only on request.**
2. **Official direct channels before cold recruiter outreach.**
3. **No guessed email addresses.**
4. **No unsupported candidate claims.**
5. **The CV attachment is identified by content hash, not filename alone.**
6. **Approval attaches to exact semantic content, never to an opportunity in the abstract.**
7. **Every external action produces auditable state.**
8. **Duplicate sends fail closed.**
9. **Apollo credits are never consumed implicitly.**
10. **Opportunity OS owns policy/state; ChatGPT owns connected-tool operation.**

## Architectural boundary

Recommended architecture:

```text
DailyRadarBatch HIGH/MEDIUM
        ↓
ApplicationPacket (V0.2B)
        ↓
ContactResolver + ContactPolicy
        ↓
ContactResolution
        ↓
OutreachBrief
        ↓
[ChatGPT operator boundary]
        ↓
Gmail draft creation / authorized contact lookup
        ↓
DraftSnapshot
        ↓
ApprovalRecord
        ↓
Gmail send
        ↓
SendReceipt
        ↓
OutreachLedger
```

Opportunity OS remains deterministic/offline for its core domain logic. Gmail, Apollo, web/contact lookup, and human approval happen outside the deterministic core through connected tools.

The repository does not store OAuth tokens, Gmail credentials, Apollo API keys, recruiter private exports, or real sent-message bodies in public tracked source.

## Relationship to V0.2A1 and V0.2B

V0.2A1 answers whether an opportunity is worth attention and which candidate track wins.

V0.2B produces a truthful `ApplicationPacket` with:

- opportunity identity and snapshot hash;
- selected intent and application track;
- fit/confidence/version metadata;
- selected fact/evidence IDs;
- unresolved gaps;
- validated structured CV;
- private PDF path;
- `cv_sha256`;
- semantic `packet_sha256`.

V0.2C must consume the prepared packet rather than rebuilding CV logic or reselecting candidate evidence independently.

## First-class application email extraction

V0.2A1 currently detects whether a posting contains an email and classifies `application_mode = DIRECT_EMAIL`. V0.2C closes the missing data-model gap: the actual published email address becomes typed data with provenance.

Suggested model:

```text
ApplicationContactHint
- kind: PUBLISHED_EMAIL | OFFICIAL_HR_EMAIL | RECRUITER | MANUAL_CHANNEL
- value
- source_url optional
- source_field
- source_text optional
- extraction_method
- confidence
- discovered_at
```

For a published email extracted directly from vacancy text, provenance must identify the source field/span or structured field that contained it.

The extractor may normalize case/whitespace but may not transform a guessed name/domain pattern into an email address.

## Contact policy

`ContactPolicy` defines ordered fallback behavior and the trust rules required before a contact can become actionable.

Default priority:

```text
1. PUBLISHED_VACANCY_EMAIL
2. OFFICIAL_HR_EMAIL
3. VERIFIED_RECRUITER
4. MANUAL_FORM
```

### Published vacancy email

Highest priority when explicitly present in the vacancy source or trusted normalized source data.

No enrichment cost. No additional recruiter lookup required unless the published instructions are ambiguous or unusable.

### Official Careers / HR email

May be used when supported by a direct official company/careers source. The source must be retained. Generic company email guesses such as `careers@domain`, `rrhh@domain`, or `jobs@domain` are not allowed unless the address is actually published by a trusted source.

### Verified recruiter / Talent Acquisition

Used only when stronger official application email channels are unavailable.

Identity discovery may be performed without email enrichment. A recruiter candidate is not automatically treated as responsible for the requisition. The resolution must record why the person is relevant: current employer, recruiting/TA role, geography/role affinity, or explicit posting relationship when available.

Apollo email enrichment is an external paid/credit-consuming action. Opportunity OS may emit `REQUIRES_ENRICHMENT` but cannot consume a credit or silently authorize the call.

### Manual/form channel

If no trustworthy email contact exists, V0.2C records the application mode and manual route. Form submission automation remains outside this slice.

## Contact models

Suggested strict contracts:

```text
ContactCandidate
- candidate_id
- opportunity_id
- channel
- email optional
- contact_name optional
- contact_role optional
- organization
- source_kind
- source_ref
- confidence
- verification_status
- requires_paid_enrichment
- discovered_at
```

`verification_status` initial values:

```text
VERIFIED_DIRECT
VERIFIED_OFFICIAL
IDENTITY_VERIFIED_EMAIL_UNKNOWN
VERIFIED_ENRICHED
MANUAL_ONLY
UNVERIFIED
```

`ContactResolution`:

```text
- opportunity_id
- selected_candidate_id optional
- channel
- email optional
- contact_name optional
- contact_role optional
- organization
- source_kind
- source_ref
- confidence
- verification_status
- resolution_reason
- resolved_at
- resolver_version
```

A resolution with an email intended for draft creation must not have `UNVERIFIED` status.

If no permitted contact exists, return `BLOCKED_NO_CONTACT` or `MANUAL_ONLY`; never fabricate a fallback address.

## Automatic outreach eligibility

Outreach preparation is automatic only for selected daily radar opportunities satisfying all of:

- tier is `HIGH` or `MEDIUM` for the selected lane;
- opportunity is eligible under radar hard gates;
- an `ApplicationPacket` exists and validates structurally;
- application packet opportunity identity matches the radar opportunity;
- packet CV file is present when attachment preparation is requested;
- packet `cv_sha256` matches the actual local artifact bytes;
- opportunity is not already sent/applied under ledger policy;
- no active cooldown or duplicate-contact rule blocks outreach.

`STRETCH` is diagnostic by default. A manually promoted stretch opportunity records explicit promotion provenance before entering the same preparation path.

## OutreachBrief

`OutreachBrief` is the deterministic bridge between Opportunity OS and ChatGPT. It is not the final email copy.

Suggested fields:

```text
OutreachBrief
- brief_id
- opportunity_id
- opportunity_snapshot_hash
- company
- role
- selected_intent
- application_track_id
- tier
- contact_resolution
- application_mode
- why_fit[]
- strongest_evidence[]
- selected_fact_ids[]
- selected_evidence_ids[]
- unresolved_gaps[]
- allowed_claims[]
- forbidden_claims[]
- language
- tone_policy
- call_to_action_policy
- cv_pdf_path
- cv_sha256
- application_packet_sha256
- brief_version
- brief_sha256
- created_at
```

### `why_fit`

Rule-based explanation derived from already selected verified support. It is not a new source of factual authority.

### `allowed_claims`

Claims ChatGPT may use in the email because they are backed by V0.2B facts/evidence/approved claim wording.

### `forbidden_claims`

Known tempting overclaims or unsupported interpretations, such as an exact product, duration, certification, seniority, language level, metric, employment status, or domain expertise not supported by evidence.

### `unresolved_gaps`

Important requirements not supported by verified evidence. Their presence does not automatically block outreach unless a higher-level policy says the opportunity is ineligible, but the email must not silently convert them into positive claims.

## Email copy policy

ChatGPT may write natural language, but the semantic content is bounded by `OutreachBrief + ApplicationPacket`.

Default style:

- concise;
- role/company specific;
- one clear reason for writing;
- two or three strongest verified points at most;
- simple call to action;
- no repetition of the full CV;
- no generic filler claiming passion/enthusiasm as evidence;
- no unsupported years, tools, metrics, certifications, titles, employers, degrees, languages, or outcomes.

The copy layer may rephrase approved evidence but may not upgrade support strength.

## Draft lifecycle

Gmail drafts are external resources. Opportunity OS does not own Gmail OAuth and does not create drafts autonomously.

When the user asks ChatGPT to create a draft:

1. Resolve or confirm `ContactResolution`.
2. Load the exact `OutreachBrief` and `ApplicationPacket`.
3. Verify local CV artifact bytes against `cv_sha256`.
4. Compose subject/body within the brief constraints.
5. Create Gmail draft with the exact intended recipient and CV attachment.
6. Record returned Gmail draft identity plus the semantic content supplied to Gmail.
7. Produce `DraftSnapshot`.

Suggested `DraftSnapshot`:

```text
- draft_snapshot_id
- opportunity_id
- brief_sha256
- application_packet_sha256
- provider: gmail
- provider_draft_id
- reply_message_id optional
- to[]
- cc[]
- bcc[]
- subject
- body_canonical
- attachment_sha256s[]
- cv_sha256
- content_type
- draft_sha256
- created_at
```

`draft_sha256` is computed from canonical semantic fields, not Gmail internal IDs/timestamps.

## Draft mutation and revalidation

Approval is invalidated by any semantic draft change.

Material fields include:

- `to`, `cc`, `bcc`;
- subject;
- body;
- reply/thread target;
- attachment set;
- attachment content hashes;
- selected CV hash.

ChatGPT-originated edits are easy to track: create a new `DraftSnapshot` and new `draft_sha256`.

Manual edits performed directly in Gmail require revalidation before automated send. The operator should re-read the underlying draft/message content when the connected Gmail capability exposes it and recompute the semantic snapshot.

If exact body/recipient/attachment revalidation is unavailable or ambiguous, automated send must fail closed with `BLOCKED_DRAFT_UNVERIFIABLE`. The safe fallback is to recreate a draft from the known approved canonical snapshot or let the user send manually from Gmail.

Because connected Gmail draft update operations may not support editing drafts that already contain attachments, the default automation policy is **immutable attached draft**: material edits produce a replacement draft/snapshot rather than silently mutating the approved attached draft.

## Approval model

`ApprovalRecord` is a human authorization for one exact `draft_sha256`.

Suggested fields:

```text
ApprovalRecord
- approval_id
- opportunity_id
- draft_sha256
- application_packet_sha256
- approved_by
- approval_scope: SINGLE | BATCH
- batch_manifest_sha256 optional
- approved_at
- expires_at optional
- revoked_at optional
- status
```

Single approval authorizes one exact draft hash.

Batch approval may authorize a fixed immutable manifest of draft hashes. It is never a quota or wildcard authorization. Adding, removing, or changing one member creates a different manifest hash and requires new approval.

Approval does not itself send email.

## Send gate

Before ChatGPT calls Gmail `send_draft`, the workflow must establish all of:

- user explicitly requested the send action;
- draft is revalidated or otherwise exactly matches the approved semantic snapshot;
- active `ApprovalRecord` exists for the current `draft_sha256`;
- attachment/CV hash matches the approved snapshot;
- no previous successful send exists for the same idempotency key;
- recipient remains permitted by contact policy;
- opportunity is not blocked/closed under current known state.

If any check fails, no send occurs.

## Idempotency

Suggested send idempotency key:

```text
sha256(
  opportunity_id
  + normalized primary recipient
  + application_packet_sha256
  + draft_sha256
)
```

A successful send consumes that key. Repeating the same execution request returns `BLOCKED_ALREADY_SENT` or the existing receipt rather than sending again.

A materially different recipient/body/CV creates a new hash but is still subject to application/contact cooldown and duplicate-contact policy; hash changes are not a loophole for repeated outreach.

## SendReceipt

After successful Gmail send, record a minimal external receipt:

```text
SendReceipt
- receipt_id
- opportunity_id
- approval_id
- draft_sha256
- application_packet_sha256
- idempotency_key
- provider: gmail
- provider_message_id
- provider_thread_id optional
- recipient
- sent_at
- status: SENT
```

Do not infer success because an API call was attempted. `SENT` requires the provider to return successful send evidence.

## Outreach ledger

The ledger tracks workflow state without becoming a second Gmail mailbox.

Minimum event types:

```text
PACKET_ACCEPTED
CONTACT_RESOLVED
OUTREACH_READY
DRAFT_CREATED
DRAFT_REPLACED
APPROVED
APPROVAL_INVALIDATED
SEND_ATTEMPTED
SENT
SEND_FAILED
MANUAL_ROUTE
RESPONSE_OBSERVED
```

Suggested state progression:

```text
PREPARED
→ CONTACT_RESOLVED
→ OUTREACH_READY
→ DRAFT_CREATED
→ APPROVED
→ SENT
```

Blocking/diagnostic states:

```text
BLOCKED_NO_CONTACT
BLOCKED_INVALID_PACKET
BLOCKED_CV_CHANGED
BLOCKED_DRAFT_CHANGED
BLOCKED_DRAFT_UNVERIFIABLE
BLOCKED_APPROVAL_MISSING
BLOCKED_ALREADY_SENT
BLOCKED_POLICY
MANUAL_ONLY
```

State transitions are event-driven and validated; later state cannot exist without required prior evidence.

## Contact frequency and anti-spam

Existing operational defaults remain normative:

- maximum 20 applications/day is a ceiling, never a target;
- one initial contact per requisition;
- maximum two recruiter contacts per company/day;
- known duplicate requisitions do not generate duplicate outreach;
- speculative candidature uses its own cooldown, default 30 days;
- a different draft hash does not bypass company/requisition cooldowns.

V0.2C favors one strong official channel over multi-contact blasting.

## Gmail operator contract

Gmail remains a connected ChatGPT capability rather than an embedded Opportunity OS dependency.

Expected external operations:

```text
read/search relevant thread when replying
create draft with exact attachment
review/revalidate draft
send existing draft after explicit approval
read response/thread later
```

No Gmail token, refresh token, password, mailbox export, or OAuth implementation belongs in the public repository.

## Apollo operator contract

Apollo is used only when official free application channels are insufficient and recruiter contact discovery materially improves the application path.

Rules:

1. Search recruiter/TA identities first without paid enrichment when possible.
2. Narrow to relevant candidates; do not enrich broad lists “just in case”.
3. Before any credit-consuming enrichment, show the exact scope/cost required by the connected Apollo tool and wait for explicit user confirmation.
4. Never treat an inferred corporate email pattern as verified contact data.
5. Persist only the minimal contact provenance required for the outreach ledger; do not export Apollo databases into the public repository.

## Public/private data boundary

Public repo may contain:

- strict schemas;
- policy/resolver/brief/approval/ledger code;
- fictional contacts/domains;
- deterministic hashing/idempotency code;
- tests and documentation.

Private/local-only data includes:

- real candidate master facts/evidence;
- real application PDFs/packets;
- real contact email addresses when persisted locally;
- recruiter identity/enrichment results;
- Gmail draft/message/thread IDs;
- email bodies for real applications;
- approval records tied to real applications;
- send receipts;
- OAuth/API secrets.

Suggested private paths:

```text
state/outreach.local.sqlite3
artifacts/applications/<application_id>/cv.pdf
artifacts/applications/<application_id>/outreach/*.json
```

These paths must be gitignored and covered by the tracked-private-file CI guard where applicable.

## Service boundaries

Suggested deterministic local services:

```text
ContactResolutionService.resolve(
    opportunity,
    enrichment,
    contact_hints,
    policy,
    ledger,
    now,
) -> ContactResolutionResult
```

```text
OutreachPreparationService.prepare(
    assessment,
    application_packet,
    contact_resolution,
    policy,
    now,
) -> OutreachPreparationResult
```

```text
ApprovalService.approve(
    draft_snapshot,
    approval_request,
    ledger,
    now,
) -> ApprovalRecord
```

```text
SendGate.validate(
    draft_snapshot,
    approval_record,
    ledger,
    policy,
    now,
) -> SendAuthorizationResult
```

These services do not call Gmail or Apollo directly.

External tool responses are converted into typed local events/snapshots at the operator boundary.

## Error model

Errors are typed and privacy-safe. Initial codes include:

```text
invalid_application_packet
packet_opportunity_mismatch
cv_artifact_missing
cv_hash_mismatch
contact_unavailable
contact_unverified
paid_enrichment_required
stretch_not_promoted
outreach_policy_blocked
draft_snapshot_invalid
draft_changed
draft_unverifiable
approval_missing
approval_invalid
approval_expired
already_sent
provider_send_failed
provider_receipt_invalid
```

No error should echo private email bodies, CV contents, secret tokens, or raw enrichment payloads by default.

## Persistence

V0.2C introduces a small local ledger/persistence layer independent of Gmail.

Recommended storage: SQLite, following the existing repository's preference for local deterministic persistence.

Minimum tables/entities:

- contact resolutions/candidates or immutable contact-resolution snapshots;
- outreach briefs;
- draft snapshots;
- approvals;
- send receipts;
- event ledger.

Persistence should support idempotent upsert by semantic/version keys and preserve historical events rather than mutating successful sends away.

The public repo includes schemas/migrations/tests only; the real local database is private/gitignored.

## No new autonomous daemon required

V0.2C does not need a background worker, message queue, cron service, LangChain/LangGraph agent, or autonomous email daemon.

The user and ChatGPT already provide the orchestration loop:

```text
user asks → ChatGPT reads state → connected action → result → Opportunity OS ledger update
```

This is intentionally simpler than building duplicate infrastructure.

## Testing

CI remains offline and uses fictional data/providers.

Required test areas:

### Contact extraction/resolution

- published email extracted with exact provenance;
- no guessed email patterns;
- official HR beats recruiter;
- recruiter beats manual form only when verified;
- paid enrichment remains a typed requirement, not an automatic action;
- no-contact fails closed.

### Outreach preparation

- only `HIGH`/`MEDIUM` automatic candidates;
- `STRETCH` requires explicit promotion;
- packet opportunity mismatch blocks;
- missing CV blocks when attachment required;
- CV byte hash mismatch blocks;
- allowed/forbidden claims are traceable to packet evidence;
- unsupported requirement remains gap.

### Draft hashing

- identical semantic draft content produces identical hash;
- Gmail draft ID/timestamps do not affect semantic hash;
- recipient/body/subject/reply target/attachment hash changes alter hash;
- attachment filename change alone does not alter semantic meaning when bytes/hash are unchanged, unless policy intentionally includes filename.

### Approval

- approval requires exact draft hash;
- changed draft invalidates approval;
- immutable batch manifest approval;
- adding/removing a draft invalidates batch approval;
- expired/revoked approval blocks.

### Send gate/idempotency

- no approval → no authorization;
- changed CV → no authorization;
- already-sent key → no second send;
- failed provider attempt does not become `SENT`;
- valid provider receipt records one successful send;
- different hash does not bypass requisition/company cooldown.

### Privacy/regression

- all V0.1/V0.2A/V0.2B tests remain green;
- real local ledger/outreach artifacts forbidden from tracked source;
- fictional public fixtures only;
- no network required in CI.

## Initial operational slice

The first usable implementation should prioritize the smallest path that can be exercised on real opportunities:

```text
ApplicationPacket
→ published/known verified email
→ OutreachBrief
→ ChatGPT-created Gmail draft with CV
→ DraftSnapshot
→ explicit approval
→ SendGate
→ Gmail send
→ SendReceipt + ledger
```

Recruiter discovery/enrichment can be layered onto the same contracts immediately after the direct-email path works. This avoids blocking real usage on Apollo integration complexity.

## Deliberate exclusions

Not V0.2C:

- autonomous bulk email blasting;
- automatic Gmail draft creation without user request;
- Gmail OAuth/token implementation inside Opportunity OS;
- Apollo sequence/campaign automation;
- paid enrichment without explicit confirmation;
- guessed recruiter emails;
- automated browser/ATS form submission;
- legal/sensitive declaration completion;
- CAPTCHA bypass;
- automatic acceptance of terms;
- LLM-generated facts or authority over evidence;
- rewriting CV facts outside V0.2B validation;
- target-account scoring implementation (V0.2A2 remains separate/deferred);
- full outcome analytics/calibration (V0.2D);
- full compact cross-tool Context Bridge snapshot (V0.2E).

## Success criteria

V0.2C is complete when fictional integration tests can take a valid V0.2B `ApplicationPacket`, resolve the highest-priority permitted contact without guessing, prepare a deterministic evidence-bounded `OutreachBrief`, produce a semantic `DraftSnapshot`, require exact hash-bound human approval, block altered/unverifiable drafts, enforce send idempotency/cooldowns, accept a successful fictional Gmail send receipt, and record an auditable ledger event chain — while no deterministic core service directly calls Gmail/Apollo and all prior radar/CV/privacy tests remain green.

Operationally, the first real-world milestone is reached when ChatGPT can use those contracts to prepare a real application draft with the exact validated CV, let the user review it, send only on explicit approval, and register the result safely.