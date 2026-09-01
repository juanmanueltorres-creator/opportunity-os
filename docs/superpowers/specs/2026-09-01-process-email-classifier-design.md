# Process Email Classifier Design

Date: 2026-09-01
Status: Approved design for implementation planning
Target repository: `juanmanueltorres-creator/opportunity-os`

## 1. Problem

Opportunity OS can already read explicitly selected Gmail metadata, produce constrained `OperatorObservation` records, preview state transitions, require explicit confirmation, and import confirmed observations into Relationship Memory. Search Health can then report observed process evidence with explicit coverage.

The missing layer is semantic interpretation of process-related email content. A selected inbound message may explicitly mean that an application was received, an interview was proposed, a hiring stage advanced, a process changed, an offer was made, or a rejection occurred. Today the system cannot distinguish those lifecycle facts from generic replies without manual interpretation.

The goal of this slice is to classify one explicitly selected inbound Gmail message into a small, auditable set of hiring-process signals, show the exact evidence used during preview, derive at most one candidate `OperatorObservation`, and still require the existing human confirmation path before Relationship Memory changes.

The classifier proposes a process fact. The operator decides whether that fact enters Relationship Memory.

## 2. Non-goals

V1 does not:

- scan or synchronize the Gmail mailbox;
- classify messages in the background;
- classify complete Gmail threads;
- classify the operator's own outbound messages as hiring-process evidence;
- send messages, applications, follow-ups, or any external action;
- use an external LLM by default;
- persist Gmail body text, HTML, subject text, quoted history, signatures, or literal evidence spans;
- read or classify attachments, PDFs, images, calendar files, or external links;
- infer recruiter intent, hiring probability, sentiment, salary, company, role, or causal success;
- fabricate historical `PROCESS_OPENED` events merely to make later events fit;
- treat an ATS acknowledgement as an active hiring process;
- introduce a separate persisted classification ledger;
- change Search Health semantics in this slice;
- add a public CLI for message classification.

## 3. Existing boundaries to preserve

The current Gmail Read adapter remains metadata-only. Its existing `format=metadata` behavior and `/api/v1/adapters/gmail/observe` contract must not be silently widened to fetch bodies.

The existing Operator Bridge remains the only import boundary into Relationship Memory:

```text
OperatorObservation
    -> operator preview
    -> explicit human confirmation
    -> operator import
    -> RelationshipEvent
    -> Relationship Memory
```

The Process Email Classifier must not write Relationship Memory directly.

The existing stale-preview protection remains authoritative. If relationship state changes after classification/preview but before import, the Operator Bridge may block the import as stale.

## 4. Architecture

Use a separate process-email layer rather than embedding lifecycle semantics inside the Gmail adapter.

```text
Explicit inbound Gmail message selection
        |
        v
Gmail Content Reader
  - full content for this selected message only
  - transient body/subject
  - no persistence
        |
        v
ProcessClassifier interface
        |
        v
DeterministicProcessClassifier V1
  - ES + EN rules
  - signals[]
  - categorical confidence
  - transient evidence spans
        |
        v
ProcessEventProjector
  + current RelationshipAccount
        |
        +--> no mutation candidate
        +--> PROCESS_OPENED
        +--> PROCESS_UPDATED
        +--> PROCESS_CLOSED
        |
        v
ProcessEmailPreview
  - classification evidence visible
  - proposed observation visible
  - existing Operator Bridge preview embedded when applicable
        |
        v
human confirmation
        |
        v
existing Operator Bridge import
        |
        v
Relationship Memory
```

Suggested module boundaries:

```text
app/
  adapters/
    gmail_read/          # existing metadata-only adapter
    gmail_content/       # explicit transient body read
  process_email/
    models.py
    classifier.py
    deterministic.py
    projector.py
    service.py
    api.py
  operator_bridge/       # existing import boundary
  relationships/         # existing domain state
```

`gmail_content` transports selected content. `process_email` interprets lifecycle meaning. `operator_bridge` owns import authority.

## 5. Explicit content-read boundary

V1 classifies exactly one `message_id` per request. Thread classification is out of scope.

The Gmail Content Reader must use full-content retrieval only for the explicitly selected message. It must not expose mailbox-wide enumeration, scanning, background synchronization, implicit neighboring-message reads, or attachment fetches.

The selected message must be inbound relative to the configured owned Gmail addresses. Direction detection must reuse the same ownership semantics as the existing Gmail Read flow. An outbound/self-authored message is an invalid process-email selection and produces no classification candidate.

The existing metadata-only adapter remains unchanged for existing flows.

A separate feature flag controls the more sensitive body-reading capability:

```text
OPPORTUNITY_PROCESS_EMAIL_ENABLED=false
```

Enabling `OPPORTUNITY_GMAIL_READ_ENABLED` must not implicitly enable process-email content reads.

## 6. Transient email model and MIME parsing

The content layer may construct an in-memory model conceptually equivalent to:

```text
TransientEmailContent
- message_id
- thread_id
- internal_date
- from_address
- subject
- current_message_text
```

`subject` and `current_message_text` are transient and must not be written to Relationship Memory, operator receipts, generated artifacts, structured logs, or persisted classifier records.

The Gmail FULL parser must:

1. decode Gmail base64url body data;
2. traverse nested multipart payloads recursively;
3. ignore parts with attachment disposition or attachment filenames;
4. prefer a usable `text/plain` body;
5. otherwise convert a usable `text/html` body to text without script/style content;
6. strip or isolate quoted replies and obvious signatures;
7. normalize whitespace;
8. classify only the current-message portion.

Attachments are neither fetched for classification nor parsed in V1.

The maximum decoded candidate message text accepted for classification is 256 KiB. Content beyond the bound is not silently truncated for semantic classification; the request fails closed with a content-too-large error and no mutation candidate.

If current-message text cannot be separated from quoted history with sufficient confidence, return an ambiguous parsing result and propose no mutation.

## 7. Lifecycle signal taxonomy

`ProcessSignalKind` contains only positive/observed lifecycle signal types:

```text
APPLICATION_ACKNOWLEDGED
INTERVIEW_PROPOSED
STAGE_ADVANCED
PROCESS_UPDATED
OFFER_RECEIVED
REJECTED
```

Semantics:

| Signal | Meaning | Can drive Relationship Memory mutation? |
|---|---|---|
| `APPLICATION_ACKNOWLEDGED` | provider/employer confirms receipt or registration of the application | no |
| `INTERVIEW_PROPOSED` | explicit invitation or request to schedule an interview/conversation | yes |
| `STAGE_ADVANCED` | explicit advancement to a subsequent hiring stage | yes |
| `PROCESS_UPDATED` | material update inside an already known process | only when a process is open |
| `OFFER_RECEIVED` | explicit employment offer | yes |
| `REJECTED` | explicit rejection or process closure | only when a process is open |

`APPLICATION_ACKNOWLEDGED` is deliberately not equivalent to `PROCESS_OPENED`.

Classification disposition is separate from signal kinds:

```text
CLASSIFIED
NOT_PROCESS
AMBIGUOUS
```

`NOT_PROCESS` means there is sufficient evidence that the message does not represent any supported lifecycle signal. `AMBIGUOUS` means the available evidence is insufficient or contradictory. Neither is stored inside `signals[]`.

## 8. Multi-signal classification and mutation selection

A message may produce more than one compatible lifecycle signal. The classifier must preserve those signals instead of forcing a single label.

Example:

```text
"We received your application and would like to invite you to an interview."

signals:
- APPLICATION_ACKNOWLEDGED
- INTERVIEW_PROPOSED

candidate mutation:
- PROCESS_OPENED
```

A classification request may yield at most one candidate `OperatorObservation`.

Signal retention and mutation selection are separate concerns. Lower-level evidence is not discarded merely because a more lifecycle-significant signal determines the candidate mutation.

For compatible positive signals, the mutation-driving semantic priority is:

```text
OFFER_RECEIVED
  > STAGE_ADVANCED
  > INTERVIEW_PROPOSED
  > PROCESS_UPDATED
  > APPLICATION_ACKNOWLEDGED
```

This priority selects the mutation-driving signal; it does not delete the other compatible signals from the preview.

`REJECTED` may coexist with `APPLICATION_ACKNOWLEDGED`, in which case `REJECTED` drives projection. `REJECTED` combined with `INTERVIEW_PROPOSED`, `STAGE_ADVANCED`, `PROCESS_UPDATED`, or `OFFER_RECEIVED` is treated as a lifecycle conflict unless a future design introduces role-specific disambiguation.

## 9. Confidence model

Confidence is categorical:

```text
HIGH
MEDIUM
LOW
```

No probability-like scores are used in V1.

Confidence is determined by which explicit deterministic rule was satisfied.

- `HIGH`: explicit, unambiguous lifecycle statement.
- `MEDIUM`: strong contextual evidence that still requires some semantic composition.
- `LOW`: weak or generic process language.

`LOW` signals may be shown for review but can never produce a candidate `OperatorObservation`.

If all observed signals are LOW, the response is non-mutating and includes `low_confidence_only`.

## 10. Deterministic classifier contract

Expose a stable `ProcessClassifier` interface so a future optional backend could exist without changing the service contract.

V1 uses a local deterministic implementation by default. It sends no body text to an external model or third-party classifier.

The deterministic classifier is versioned:

```text
classifier_version = deterministic-process-email-v1
ruleset_version = es-en-2026-09-v1
```

Given the same normalized current-message text and the same classifier/ruleset versions, the signal result must be deterministic.

V1 explicitly supports Spanish and English rule families.

## 11. Evidence rules

Rules must be evidence compositions, not single-keyword triggers.

For example, an interview signal should require a compatible combination such as:

```text
interview/conversation concept
+ invitation/scheduling/request concept
+ recipient-directed context
```

The presence of the word `interview` alone is insufficient.

Each positive rule should capture the exact transient text span that justified the signal. Evidence spans exist only for preview and are not persisted after the request lifecycle.

Rules must explicitly handle at least:

- negation;
- hypothetical language;
- generic descriptions of the employer's process;
- quoted historical content;
- contradictory lifecycle statements.

Examples that must not become `INTERVIEW_PROPOSED`:

```text
"We are not yet scheduling interviews."
"If selected, you may be invited to interview."
"Our interview process normally takes two weeks."
```

## 12. Rejection and offer thresholds

`REJECTED` requires explicit closure/rejection language. Delay, continued review, or lack of a decision are not rejection.

`OFFER_RECEIVED` requires explicit offer language. Compensation-range discussion alone is not an offer.

Both classes prefer false negatives over false positives.

## 13. Contradictions and fail-closed behavior

Conflicting lifecycle signals must not be resolved by arbitrary precedence when they may refer to different roles or contexts.

Example:

```text
"This position has been filled, but we would like to interview you for another opportunity."
```

may produce conflicting `REJECTED` and `INTERVIEW_PROPOSED` evidence.

V1 returns `AMBIGUOUS`, no candidate mutation, and:

```text
conflicting_process_signals
```

The operator interprets the message manually.

## 14. Relationship-state projection

Candidate event projection depends on the current `RelationshipAccount` state.

| Mutation-driving signal | `open_process = false` | `open_process = true` |
|---|---|---|
| `APPLICATION_ACKNOWLEDGED` | no mutation | no mutation |
| `INTERVIEW_PROPOSED` | `PROCESS_OPENED` | `PROCESS_UPDATED` |
| `STAGE_ADVANCED` | `PROCESS_OPENED` | `PROCESS_UPDATED` |
| `PROCESS_UPDATED` | no mutation + `no_open_process_to_update` | `PROCESS_UPDATED` |
| `OFFER_RECEIVED` | `PROCESS_OPENED` | `PROCESS_UPDATED` |
| `REJECTED` | no mutation + `no_open_process_to_close` | `PROCESS_CLOSED` |

An explicit offer with no known open process may establish that a real process exists now, therefore V1 may propose `PROCESS_OPENED`. It does not fabricate prior interview/stage events.

A generic process update with no known process does not establish enough context to open one.

A rejection with no known open process remains visible in the current response but does not fabricate `PROCESS_OPENED -> PROCESS_CLOSED` history.

## 15. Non-mutating classification lifecycle

V1 introduces no separate classification database or ledger.

Therefore classifications that do not produce an imported `OperatorObservation` are response-only:

- `APPLICATION_ACKNOWLEDGED` by itself;
- `NOT_PROCESS`;
- `AMBIGUOUS`;
- LOW-confidence-only evidence;
- `PROCESS_UPDATED` without an open process;
- `REJECTED` without an open process.

They are visible to the operator during the request but are not persisted after the request lifecycle. A future application-status or classification-history store requires a separate design.

## 16. Normalized persisted reason

When a mutation candidate exists, use a normalized reason rather than provider text:

```text
INTERVIEW_PROPOSED -> "explicit interview invitation observed"
STAGE_ADVANCED     -> "explicit hiring-stage advancement observed"
PROCESS_UPDATED    -> "explicit hiring-process update observed"
OFFER_RECEIVED     -> "explicit employment offer observed"
REJECTED           -> "explicit process rejection observed"
```

V1 does not extract or fabricate a `process_label` from body text. Existing process labels are preserved when applicable.

## 17. Typed provenance without sensitive text

The persisted event retains enough classifier provenance to audit how the candidate fact was produced without storing source content.

Extend `OperatorObservation` with one optional, typed provenance object conceptually equivalent to:

```text
ObservationSemanticProvenance
- producer = PROCESS_EMAIL_CLASSIFIER
- producer_version
- policy_version
- classification
- reason_code
```

For process-email observations:

```text
producer_version = classifier_version
policy_version = ruleset_version
classification = mutation-driving ProcessSignalKind
reason_code = machine-generated classifier reason code
```

All fields are bounded machine-generated identifiers. No arbitrary user/provider text is allowed.

Operator Bridge normalization copies only these typed values into allowlisted `RelationshipEvent.metadata` keys. It must not introduce a generic free-form provenance dictionary for process-email text.

Existing observations without semantic provenance remain valid and unchanged.

## 18. Process email API

V1 adds one process-email endpoint:

```text
POST /api/v1/process-email/preview
```

There is no process-email import endpoint. Confirmation continues through the existing Operator Bridge import API.

Request:

```text
ProcessEmailSelection
- account_id
- contact_id?
- message_id
- selected_by
```

Response:

```text
ProcessEmailPreview
- status
- classifier_version
- ruleset_version
- source_ref
- observed_at
- signals[]
    - kind
    - confidence
    - reason_code
    - evidence_spans[]      # transient response only
- warnings[]
- proposed_observation?     # at most one
- operator_preview?         # existing ObservationPreview when applicable
- external_actions = []
```

Response status must distinguish semantic disposition and infrastructure failure:

```text
CLASSIFIED
NOT_PROCESS
AMBIGUOUS
CONTENT_UNAVAILABLE
PROVIDER_ERROR
INVALID_SELECTION
BLOCKED
```

`INVALID_SELECTION` includes outbound/self-authored messages. `BLOCKED` includes missing/unknown Relationship state or unavailable Operator Bridge when a projection is required.

The process-email service must not log the full request body, normalized email content, evidence spans, or full response payload.

## 19. Confirmation flow

If the operator accepts a candidate observation, the client submits the returned `OperatorObservation` plus the existing `operator_preview.preview_sha256` to:

```text
POST /api/v1/operator/observations/import
```

with explicit `confirmed_by` and `confirmed_at`.

No process-email service method bypasses this step.

## 20. Observation identity and idempotency

The candidate observation identity is based on provider-message identity plus the mutation-driving process signal, not on classifier/ruleset version.

Conceptually:

```text
gmail-message:<message_id>:process-signal:<signal>
```

Classifier/ruleset versions describe provenance, not the identity of the real-world observation.

Existing Operator Bridge idempotency/conflict behavior remains authoritative. Re-importing an identical observation may return `ALREADY_IMPORTED`; incompatible reuse of the same observation identity remains a conflict.

## 21. Privacy contract

Transient during classification/preview:

```text
subject
plain body
HTML-derived text
literal evidence spans
quoted/signature material while parsing
```

Allowed to persist after confirmation:

```text
observation identity
account/contact identifiers already required by Relationship Memory
source_ref
observed_at
normalized reason
relationship event
typed classifier/ruleset provenance
human confirmation audit fields
```

Forbidden from persistence:

```text
raw body
HTML
subject
literal evidence spans
attachments
quoted history
signature text
arbitrary classifier/provider notes containing source text
```

Raw email content must also be excluded from generated artifacts and structured logs.

The existing operator preview hash binds the candidate observation and relationship state, not raw email content. The raw body is not part of persisted identity or persisted preview material.

## 22. Error semantics

Errors and warnings remain explicit. Expected codes include:

```text
gmail_content_unavailable
gmail_payload_invalid
gmail_unauthorized
gmail_forbidden
gmail_rate_limited
unsupported_mime
missing_usable_body
content_too_large
quoted_content_ambiguous
message_not_inbound
unknown_relationship_account
conflicting_process_signals
no_open_process_to_update
no_open_process_to_close
low_confidence_only
operator_bridge_unavailable
```

Infrastructure/uncertainty errors must not be converted to `NOT_PROCESS`.

`NOT_PROCESS` means there is sufficient evidence that no supported lifecycle signal is present. `AMBIGUOUS` means there is not enough defensible evidence or the observed signals conflict.

## 23. Testing strategy

### Unit tests

Cover:

- Gmail base64url decoding;
- recursive multipart traversal;
- attachment exclusion;
- 256 KiB bound and fail-closed oversize behavior;
- plain-text preference;
- HTML fallback and script/style exclusion;
- quote/signature stripping;
- inbound/outbound selection validation;
- deterministic ES/EN rule families;
- negation;
- hypothetical language;
- generic process descriptions;
- confidence assignment;
- multi-signal retention;
- deterministic mutation-driving priority;
- contradiction detection.

### Domain tests

Cover:

- signal-to-event projection;
- `open_process` state dependence;
- `APPLICATION_ACKNOWLEDGED` never opening a process;
- `PROCESS_UPDATED` without open process producing no event;
- `REJECTED` without open process producing no close;
- `OFFER_RECEIVED` without open process proposing `PROCESS_OPENED`;
- LOW confidence producing no mutation;
- non-mutating classifications producing no persisted classification state.

### Integration tests

Cover:

```text
explicit inbound Gmail FULL fixture
  -> transient content
  -> deterministic classification
  -> candidate OperatorObservation
  -> existing Operator Bridge preview
  -> confirmed existing Operator Bridge import
  -> RelationshipEvent
```

Also verify stale-preview blocking when relationship state changes between preview and import.

### Privacy regression tests

Tests must fail if raw body, HTML, subject, or literal evidence spans appear in:

- persistable `OperatorObservation` fields outside the typed provenance contract;
- RelationshipEvent persisted metadata;
- import receipts;
- Relationship SQLite rows;
- generated artifacts;
- structured logs covered by the test harness.

### Required semantic regressions

At minimum:

- ATS receipt != `PROCESS_OPENED`;
- outbound operator email != process classification;
- rejection without open process != fabricated lifecycle;
- quoted historical interview text != current interview invitation;
- compensation range != `OFFER_RECEIVED`;
- hypothetical interview != `INTERVIEW_PROPOSED`;
- LOW confidence -> zero mutation;
- conflicting process signals -> zero mutation.

The full pre-existing test suite remains green in addition to new tests.

## 24. Success criteria

The slice is complete only when the repository can demonstrate all of the following:

1. The operator explicitly selects one inbound Gmail message.
2. Only that message is fetched with content for classification.
3. Outbound/self-authored messages are rejected as invalid selections.
4. Body/subject are handled transiently within the bounded content parser.
5. The classifier returns typed lifecycle signals with evidence and categorical confidence, or an explicit non-process/ambiguous disposition.
6. Application acknowledgement does not open a process.
7. An explicit interview or stage advancement proposes `PROCESS_OPENED` or `PROCESS_UPDATED` according to current state.
8. An explicit offer is preserved as `OFFER_RECEIVED` semantics.
9. A rejection only proposes `PROCESS_CLOSED` for an existing open process.
10. LOW confidence, contradiction, or ambiguity produces no mutation candidate.
11. The preview shows why the classifier reached its conclusion.
12. The preview shows the existing relationship state transition when a mutation is proposed.
13. Relationship SQLite does not change without explicit confirmation.
14. Confirmed changes enter through the existing Operator Bridge.
15. A stale relationship state can block a previously generated preview.
16. Non-mutating classifications are not silently persisted in a new store.
17. Body, HTML, subject, and literal evidence spans are not persisted.
18. Persisted semantic provenance is typed and contains only bounded machine-generated identifiers.
19. There is no mailbox scan or background sync.
20. There is no external LLM call in default V1 behavior.
21. Existing and new tests, privacy regressions, compile checks, diff checks, and CI are green on the exact implementation head.

## 25. Future extension points

The architecture intentionally leaves room for:

- a future optional classifier backend behind the stable `ProcessClassifier` interface;
- additional languages/ruleset versions;
- other conversation providers that can produce the same process-classification input contract;
- thread-level reasoning after a separate design establishes safe chronology semantics;
- a separate application-status/classification ledger if real usage proves non-mutating evidence should persist;
- Search Health extension for explicit offer-level outcomes once enough defensible observed history exists.

None of these are part of V1.

## 26. Core invariants

```text
selected inbound message != mailbox sync
body access != body persistence
classification != authority
application acknowledgement != open process
signal evidence != relationship mutation
LOW / ambiguous / conflicting != mutation
historical gap != permission to fabricate lifecycle
classifier provenance != provider content
non-mutating classification != hidden persistence
human confirmation remains mandatory
```
