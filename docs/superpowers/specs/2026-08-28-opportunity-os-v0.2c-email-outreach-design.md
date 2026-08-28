# Opportunity OS — V0.2C Email-first + Approval Design

Date: 2026-08-28
Status: approved
Base: `main` at `2f3b0676c64eb6f7cb9831c57ff85258d5e2ced0` (V0.2A1 + V0.2B merged)
Parent roadmap: private Opportunity OS operational context in the knowledge vault

## Purpose

V0.2C turns a prepared V0.2B `ApplicationPacket` into a safe outreach workflow that can be operated from ChatGPT using connected Gmail and, only when necessary, Apollo or other authorized contact sources.

The practical goal is:

```text
HIGH/MEDIUM opportunity
→ validated ApplicationPacket + CV
→ best permitted contact
→ deterministic OutreachBrief
→ ChatGPT-created Gmail draft
→ exact DraftSnapshot
→ explicit ApprovalRecord
→ separate explicit SendRequest
→ Gmail send
→ SendReceipt + OutreachLedger
```

The first implementation should be usable quickly on real applications and then hardened from real usage. It must never invent claims, guess email addresses, consume Apollo credits silently, create Gmail drafts automatically, or treat an approval as a standing authorization to send.

## Approved product decisions

### Contact priority

```text
published vacancy email
→ official Careers / HR application email
→ verified recruiter / Talent Acquisition contact
→ manual/form channel
```

Official direct channels beat cold recruiter outreach.

### Radar scope

- `HIGH` and `MEDIUM`: outreach artifacts may be prepared automatically.
- `STRETCH`: diagnostic only unless manually promoted.
- Hard-ineligible opportunities never enter outreach.

### Gmail boundary

Opportunity OS does not create Gmail drafts automatically. ChatGPT creates a draft only when the user asks.

### Copy boundary

Opportunity OS does not embed an LLM for email prose. It produces a structured `OutreachBrief`; ChatGPT writes the human-readable mail using only `OutreachBrief + ApplicationPacket` as factual authority.

### Apollo boundary

Apollo is an optional fallback. Identity search may happen without enrichment. Any operation that consumes Apollo credits requires the exact explicit confirmation required by the connected Apollo tool before execution.

### Approval boundary

Approval is bound to one exact semantic draft hash, or to one immutable manifest of exact draft hashes for a batch.

Changing recipient, subject, body, reply/thread target, attachment filename, attachment bytes, or selected CV invalidates the approval.

### Send boundary

**Approval is not a send command.** Sending requires a second, explicit user action represented as a separate `SendRequest`.

## Core principles

1. Truth before conversion.
2. Prepare automatically; perform external actions only on request.
3. Official application channels before recruiter outreach.
4. Never guess an email address.
5. No unsupported candidate claims.
6. CV identity uses filename plus content SHA-256.
7. Approval binds exact semantic content.
8. A valid approval can never send by itself.
9. Duplicate sends fail closed.
10. Apollo credits are never consumed implicitly.
11. Opportunity OS owns deterministic policy/state; ChatGPT owns connected-tool operation.
12. Real personal/contact/mail state stays private and gitignored.

## Architecture

```text
DailyRadarBatch item
        ↓
ApplicationPacket (V0.2B)
        ↓
ContactResolutionService
        ↓
ContactResolution
        ↓
OutreachPreparationService
        ↓
OutreachBrief
        ↓
──────── ChatGPT operator boundary ────────
        ↓
Gmail draft / optional authorized contact lookup
        ↓
DraftSnapshot
        ↓
ApprovalService
        ↓
ApprovalRecord
        ↓
explicit SendRequest
        ↓
SendGate
        ↓
Gmail send_draft
        ↓
SendReceipt
        ↓
OutreachLedger
```

The deterministic core does not call Gmail or Apollo directly.

## Relationship to V0.2A1 and V0.2B

V0.2A1 decides whether an opportunity deserves attention and which candidate track wins.

V0.2B produces a validated `ApplicationPacket` containing, among other fields:

- opportunity identity and snapshot hash;
- selected intent/track;
- fit/confidence/version metadata;
- selected fact/evidence IDs;
- unresolved gaps;
- validated structured CV;
- private PDF path;
- `cv_sha256`;
- semantic `packet_sha256`.

V0.2C consumes that packet. It does not independently rewrite CV evidence or re-decide which track is allowed.

## First-class published email extraction

V0.2A1 already detects the presence of an explicit email and can classify `application_mode = DIRECT_EMAIL`, but it does not expose the actual address as a typed first-class value.

V0.2C closes that gap.

Suggested contract:

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

For a vacancy-published email, provenance must identify the structured field or supporting source span.

Normalization may casefold/trim the address. It may not infer an address from a person name or corporate domain pattern.

## Contact resolution

### ContactPolicy

Default ranking:

```text
PUBLISHED_VACANCY_EMAIL
> OFFICIAL_HR_EMAIL
> VERIFIED_RECRUITER
> MANUAL_FORM
```

### Published vacancy email

Highest priority when explicitly present in trusted vacancy data. No recruiter lookup is needed unless the vacancy instructions make the channel unusable or ambiguous.

### Official HR / Careers email

Permitted only when actually published by a direct official company/careers source. Addresses such as `jobs@company.com` or `rrhh@company.com` must never be generated from convention alone.

### Recruiter / TA

Used only when a stronger official email channel is unavailable.

A recruiter identity can be discovered before knowing their email. Relevance should record employer, recruiting/TA role, geography/role affinity, or an explicit relationship to the requisition when available.

An identity match is not proof that the recruiter owns the vacancy.

Paid Apollo enrichment is represented as a blocked/external requirement, not silently executed.

### Manual form

When no trustworthy email route exists, record the form/manual route. V0.2C does not automate browser submission.

## Contact contracts

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

Initial verification values:

```text
VERIFIED_DIRECT
VERIFIED_OFFICIAL
IDENTITY_VERIFIED_EMAIL_UNKNOWN
VERIFIED_ENRICHED
MANUAL_ONLY
UNVERIFIED
```

```text
ContactResolution
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

An email resolution intended for draft creation cannot be `UNVERIFIED`.

No permitted contact returns `BLOCKED_NO_CONTACT` or `MANUAL_ONLY`. It never fabricates an address.

## Automatic outreach eligibility

Automatic preparation requires all of:

- selected tier is `HIGH` or `MEDIUM`;
- radar hard eligibility passes;
- a valid `ApplicationPacket` exists;
- packet opportunity identity matches the opportunity;
- CV artifact exists when attachment is required;
- actual CV bytes match packet `cv_sha256`;
- ledger has no existing successful application/send conflict;
- cooldown/duplicate policies allow contact.

A `STRETCH` item must carry explicit manual-promotion provenance before it can use the same pipeline.

## OutreachBrief

`OutreachBrief` is the deterministic bridge consumed by ChatGPT. It is not the final email body.

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
- cv_filename
- cv_sha256
- application_packet_sha256
- brief_version
- brief_sha256
- created_at
```

### Claim policy

`why_fit` and `strongest_evidence` are explanations derived from already verified support; they are not new factual authority.

`allowed_claims` contains only claims supported by V0.2B facts/evidence/approved wording.

`forbidden_claims` explicitly protects against tempting overclaims: unsupported exact products, durations, certifications, seniority, metrics, language levels, employment status, education, or domain expertise.

`unresolved_gaps` remains visible. A gap is never silently converted into a positive statement in the mail.

## Email copy policy

ChatGPT may phrase the email naturally, but semantic claims are bounded by `OutreachBrief + ApplicationPacket`.

Default mail style:

- concise;
- specific to the role/company;
- one clear reason for writing;
- two or three strongest verified points maximum;
- simple call to action;
- do not reproduce the CV;
- no generic filler presented as evidence;
- no unsupported tools, years, metrics, titles, companies, certifications, degrees, languages, or outcomes.

The copy layer may rephrase support; it may not upgrade support strength.

## Draft creation

When the user asks ChatGPT to create a Gmail draft:

1. resolve/confirm `ContactResolution`;
2. load exact `OutreachBrief` and `ApplicationPacket`;
3. verify CV artifact bytes against `cv_sha256`;
4. verify the intended CV filename;
5. compose subject/body within claim policy;
6. create Gmail draft with exact recipient and attachment;
7. record the provider draft identity and semantic payload supplied to Gmail;
8. create `DraftSnapshot`.

Attachment descriptor:

```text
DraftAttachment
- filename
- sha256
- role: CV | OTHER
```

Draft snapshot:

```text
DraftSnapshot
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
- attachments[]: DraftAttachment
- cv_sha256
- content_type
- draft_sha256
- created_at
```

`draft_sha256` hashes canonical semantic content including attachment filename and bytes hash. Gmail draft IDs/timestamps are excluded.

Therefore, recreating an **exact semantic replica** may keep the same `draft_sha256` even if Gmail returns a new `provider_draft_id`. Approval is about what will be sent, not Gmail's internal resource identifier.

## Draft mutation and revalidation

Material changes include:

- `to`, `cc`, `bcc`;
- subject;
- body;
- reply/thread target;
- attachment set;
- attachment filenames;
- attachment hashes;
- selected CV hash.

Any material change generates a new `DraftSnapshot` and invalidates approval for the old hash.

### ChatGPT edits

Changes performed through ChatGPT are known inputs and can deterministically produce a new snapshot/hash.

### Manual Gmail edits

If the user edits the draft directly in Gmail, automated send must revalidate the actual stored draft before sending when connector capabilities allow exact readback.

If body, recipient, thread target, filename, or attachment content cannot be revalidated exactly, return `BLOCKED_DRAFT_UNVERIFIABLE`.

Safe fallbacks:

1. recreate a new draft from the known canonical approved snapshot; if it is semantically identical, the same hash may remain valid after revalidation; or
2. leave automated workflow and let the user send manually in Gmail.

Connected Gmail tooling may not allow editing drafts containing attachments. Default automation policy is therefore **immutable attached draft**: a material change creates a replacement draft/snapshot instead of silently editing the attached draft.

## Approval model

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

Single approval authorizes one exact `draft_sha256`.

Batch approval authorizes only an immutable manifest of exact draft hashes. Adding/removing/changing one member changes the manifest hash and requires new approval.

**Approval does not create a send request and cannot cause external execution by itself.**

## Explicit SendRequest

A send requires a fresh user instruction such as “send it”, “mandalo”, or an equally explicit action tied to the draft(s) under discussion.

That intent is represented separately:

```text
SendRequest
- request_id
- opportunity_id
- draft_sha256
- requested_by
- requested_at
- approval_id
- batch_manifest_sha256 optional
```

`SendRequest` is execution intent, not long-lived authorization. It must refer to the currently approved draft hash/approval.

No `SendRequest` → no `SendAuthorization`, even when a valid `ApprovalRecord` exists.

## SendGate

Suggested service:

```text
SendGate.validate(
    draft_snapshot,
    approval_record,
    send_request,
    ledger,
    policy,
    now,
) -> SendAuthorizationResult
```

Before ChatGPT calls Gmail `send_draft`, the gate must establish all of:

- explicit `SendRequest` exists for this exact draft;
- active approval exists for current `draft_sha256`;
- request references that approval/draft;
- draft has been revalidated or exactly reconstructed from the approved snapshot;
- attachment filenames/hashes and selected CV hash match;
- recipient remains permitted by contact policy;
- no successful idempotency key already exists;
- opportunity is not currently blocked/closed under known state;
- cooldown/duplicate rules allow send.

Any failure means no send.

## Send idempotency

Initial semantic key:

```text
sha256(
  opportunity_id
  + normalized primary recipient
  + application_packet_sha256
  + draft_sha256
)
```

A successful send consumes the key. A repeated request returns the existing receipt or `BLOCKED_ALREADY_SENT`; it does not send twice.

Changing draft content produces a new hash but does not bypass requisition/company cooldown or duplicate rules.

## SendReceipt

`SENT` is recorded only after Gmail returns successful send evidence.

```text
SendReceipt
- receipt_id
- opportunity_id
- approval_id
- send_request_id
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

A provider attempt without a valid success receipt is not `SENT`.

## Outreach ledger

The ledger is an audit/state layer, not a duplicate mailbox.

Minimum event types:

```text
PACKET_ACCEPTED
CONTACT_RESOLVED
OUTREACH_READY
DRAFT_CREATED
DRAFT_REPLACED
APPROVED
APPROVAL_INVALIDATED
SEND_REQUESTED
SEND_ATTEMPTED
SENT
SEND_FAILED
MANUAL_ROUTE
RESPONSE_OBSERVED
```

Expected progression:

```text
PREPARED
→ CONTACT_RESOLVED
→ OUTREACH_READY
→ DRAFT_CREATED
→ APPROVED
→ SEND_REQUESTED
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
BLOCKED_SEND_REQUEST_MISSING
BLOCKED_ALREADY_SENT
BLOCKED_POLICY
MANUAL_ONLY
```

Later states require evidence for all required prior transitions.

## Contact frequency / anti-spam

Defaults preserved from the Opportunity OS design:

- maximum 20 applications/day is a ceiling, never a quota;
- one initial contact per requisition;
- maximum two recruiter contacts/company/day;
- known duplicate requisitions do not create duplicate outreach;
- speculative candidature cooldown defaults to 30 days;
- altered hashes cannot bypass company/requisition cooldowns.

Prefer one strong official channel over multi-contact blasting.

## Gmail operator contract

Gmail is a connected ChatGPT capability, not an embedded Opportunity OS dependency.

Expected external actions:

```text
read/search relevant thread when replying
create draft with exact attachment
review/revalidate draft
send existing draft after explicit SendRequest + valid approval
read response/thread later
```

No Gmail OAuth implementation, tokens, passwords, or mailbox exports belong in public source.

## Apollo operator contract

Apollo is used only when stronger free/official contact routes are unavailable and recruiter discovery materially helps.

1. Search recruiter/TA identities without paid enrichment where possible.
2. Narrow scope before enrichment.
3. Follow connected Apollo's exact mandatory credit-confirmation wording before any paid enrichment.
4. Never infer corporate emails.
5. Store only minimal provenance needed for local outreach state.
6. Do not use Apollo sequences/campaigns in V0.2C.

## Public/private boundary

Public source may contain:

- schemas/contracts;
- policy/resolver/brief/approval/send-gate code;
- deterministic hashing/idempotency;
- fictional contacts/domains/messages;
- tests and documentation.

Private/local-only:

- real candidate facts/evidence;
- real PDFs/ApplicationPackets;
- real contact addresses/recruiter results;
- Gmail IDs;
- real email bodies;
- approvals/send requests/receipts for real applications;
- OAuth/API secrets;
- real outreach ledger database.

Suggested private paths:

```text
state/outreach.local.sqlite3
artifacts/applications/<application_id>/cv.pdf
artifacts/applications/<application_id>/outreach/*.json
```

They must be gitignored and CI-guarded where applicable.

## Deterministic service boundaries

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
    send_request,
    ledger,
    policy,
    now,
) -> SendAuthorizationResult
```

None calls Gmail/Apollo directly.

## Error model

Initial privacy-safe codes:

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
send_request_missing
send_request_invalid
already_sent
provider_send_failed
provider_receipt_invalid
```

Errors do not echo real email bodies, CV contents, raw enrichment payloads, or tokens by default.

## Persistence

Use local SQLite, consistent with current project patterns.

Minimum durable entities:

- contact-resolution snapshots;
- outreach briefs;
- draft snapshots;
- approvals;
- send requests/events;
- send receipts;
- event ledger.

Persist semantic/version keys idempotently and preserve successful historical events.

Real database is private/gitignored.

## No autonomous daemon

No background worker, queue, cron service, LangChain/LangGraph agent, or autonomous mail daemon is required.

The operator loop is intentionally:

```text
user request
→ ChatGPT reads exact Opportunity OS state
→ connected external action
→ typed result
→ ledger update
```

## Testing

CI remains offline with fictional providers/data.

### Contact extraction/resolution

- published email has exact provenance;
- email guessing is impossible;
- official HR beats recruiter;
- verified recruiter beats manual form only when appropriate;
- paid enrichment remains an external requirement;
- no contact fails closed.

### Outreach preparation

- only `HIGH`/`MEDIUM` automatic candidates;
- stretch requires promotion;
- packet mismatch blocks;
- missing CV blocks attachment flow;
- CV bytes/hash mismatch blocks;
- allowed/forbidden claims trace to packet evidence;
- unsupported requirement stays a gap.

### Draft hashing

- same semantic content → same hash;
- Gmail draft ID/timestamps do not change hash;
- recipient/subject/body/reply target changes change hash;
- attachment filename change changes hash;
- attachment bytes/hash change changes hash;
- recreated exact semantic draft can preserve hash despite a new provider draft ID.

### Approval

- exact draft hash required;
- draft mutation invalidates approval;
- batch manifest immutable;
- expiry/revocation blocks.

### SendRequest / SendGate

- valid approval without `SendRequest` blocks;
- `SendRequest` for different hash blocks;
- changed CV blocks;
- already-sent key blocks second send;
- changed hash cannot bypass requisition/company cooldown;
- failed provider attempt is not `SENT`;
- valid provider receipt records exactly one successful send.

### Privacy/regression

- all V0.1/V0.2A/V0.2B tests stay green;
- real local state/artifacts cannot be tracked;
- public fixtures are fictional;
- CI requires no network.

## Initial operational slice

The first real-use path is intentionally smaller than the complete design:

```text
valid ApplicationPacket
→ published/known verified email
→ OutreachBrief
→ ChatGPT Gmail draft + exact CV
→ DraftSnapshot
→ user approval
→ separate user “send” action / SendRequest
→ SendGate
→ Gmail send
→ SendReceipt + ledger
```

Recruiter discovery/Apollo enrichment layers onto the same contracts after direct-email workflow works. It must not block the first usable version.

## Deliberate exclusions

Not V0.2C:

- autonomous bulk blasting;
- automatic Gmail drafts without user request;
- Gmail OAuth/token implementation inside repo;
- Apollo campaign/sequence automation;
- paid enrichment without explicit confirmation;
- guessed emails;
- browser/ATS form submission automation;
- CAPTCHA bypass;
- legal/sensitive declarations;
- automatic acceptance of terms;
- LLM-created factual authority;
- rewriting V0.2B evidence rules;
- V0.2A2 target-account scoring;
- full V0.2D learning/calibration;
- full V0.2E Context Bridge implementation.

## Success criteria

V0.2C is complete when fictional integration tests can take a valid V0.2B `ApplicationPacket`, resolve the best permitted contact without guessing, prepare a deterministic evidence-bounded `OutreachBrief`, hash an exact `DraftSnapshot`, require exact human approval, separately require a fresh explicit `SendRequest`, block changed/unverifiable drafts, enforce idempotency and cooldown policy, accept only a successful fictional Gmail receipt as `SENT`, and record an auditable ledger chain — while no deterministic core service directly calls Gmail/Apollo and every previous radar/CV/privacy test remains green.

The first real-world milestone is reached when ChatGPT can use those contracts to prepare a real Gmail draft with the exact validated CV, let the user review it, send only after explicit approval plus a separate explicit send command, and register the result safely.
