# Process Email Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, deterministic ES/EN process-email classifier for one explicitly selected inbound Gmail message, show transient evidence in preview, derive at most one candidate process observation, and keep the existing Operator Bridge as the only confirmed write path into Relationship Memory.

**Architecture:** Preserve the existing metadata-only Gmail adapter and add a separate `gmail_content` transport for explicit FULL-message reads. A new `process_email` package owns typed classification, deterministic rules, relationship-aware event projection and preview orchestration; raw email text remains request-local. When a mutation is defensible, the service creates one typed `OperatorObservation`, asks the existing Operator Bridge for the state transition preview, and leaves confirmation/import to the existing `/api/v1/operator/observations/import` endpoint.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, `httpx`, stdlib `base64`, stdlib `html.parser`, `re`, pytest/pytest-asyncio. No new runtime dependency and no external LLM call in V1.

**Spec:** `docs/superpowers/specs/2026-09-01-process-email-classifier-design.md`

## Global Constraints

- The existing Gmail Read adapter remains `format=metadata`; `/api/v1/adapters/gmail/observe` must not start fetching bodies.
- V1 accepts exactly one `message_id`; thread classification, mailbox enumeration, background sync and implicit neighboring-message reads are out of scope.
- The selected message must be inbound relative to configured owned addresses; outbound/self-authored messages return `INVALID_SELECTION` with `message_not_inbound` and no candidate observation.
- Gmail FULL content is transient. Raw body, HTML, subject, quoted history, signatures and literal evidence spans must not be persisted to `OperatorObservation`, receipts, `RelationshipEvent`, SQLite, generated artifacts or structured logs.
- Decoded candidate message text is bounded to 256 KiB. Oversize content fails closed with `content_too_large`; do not truncate and classify.
- Attachments, attachment filenames, PDFs, images, `.ics` parts and external links are not fetched or classified.
- V1 classifier backend is deterministic, local and bilingual ES/EN. `classifier_version="deterministic-process-email-v1"`; `ruleset_version="es-en-2026-09-v1"`.
- `ProcessSignalKind` contains only `APPLICATION_ACKNOWLEDGED`, `INTERVIEW_PROPOSED`, `STAGE_ADVANCED`, `PROCESS_UPDATED`, `OFFER_RECEIVED`, `REJECTED`.
- Semantic dispositions are separate: `CLASSIFIED`, `NOT_PROCESS`, `AMBIGUOUS`.
- Confidence is categorical `HIGH | MEDIUM | LOW`; LOW-only evidence never produces an `OperatorObservation`.
- `APPLICATION_ACKNOWLEDGED` never opens a process.
- `INTERVIEW_PROPOSED`, `STAGE_ADVANCED` and `OFFER_RECEIVED` may propose `PROCESS_OPENED` when there is no open process and `PROCESS_UPDATED` when one is already open.
- Generic `PROCESS_UPDATED` without an open process produces no mutation and warning `no_open_process_to_update`.
- `REJECTED` without an open process produces no mutation and warning `no_open_process_to_close`; never fabricate a retroactive open/close pair.
- `REJECTED` combined with `INTERVIEW_PROPOSED`, `STAGE_ADVANCED`, `PROCESS_UPDATED` or `OFFER_RECEIVED` is `AMBIGUOUS` with `conflicting_process_signals` and zero mutation.
- One message may retain multiple compatible signals, but a request produces at most one candidate `OperatorObservation`.
- Non-mutating classifications are response-only; V1 introduces no classification database/ledger.
- Persisted classifier provenance is typed and machine-generated only; arbitrary source text is forbidden.
- The existing Operator Bridge preview/import and stale-preview protection remain authoritative. The process-email service never writes Relationship Memory directly.
- `OPPORTUNITY_PROCESS_EMAIL_ENABLED=false` is a separate feature flag. Enabling Gmail metadata read must not enable body read.
- No public process-email CLI is added in V1.

---

## File Map

### New production files

- `app/adapters/gmail_read/direction.py` — shared owned-address and inbound/outbound semantics used by metadata read and process-email selection.
- `app/adapters/gmail_content/__init__.py` — package marker only.
- `app/adapters/gmail_content/models.py` — transient content envelope and bounded content errors/contracts.
- `app/adapters/gmail_content/normalizer.py` — Gmail FULL MIME traversal, base64url decode, plain/HTML extraction, attachment exclusion, quote/signature separation and 256 KiB guard.
- `app/adapters/gmail_content/provider.py` — explicit single-message Gmail REST FULL reader; no list/thread APIs.
- `app/process_email/__init__.py` — package marker only.
- `app/process_email/models.py` — strict request, signal, classification, projection and preview response contracts.
- `app/process_email/classifier.py` — stable `ProcessClassifier` protocol.
- `app/process_email/deterministic.py` — versioned ES/EN deterministic rule engine.
- `app/process_email/projector.py` — classification + current `RelationshipAccount` -> zero/one candidate `OperatorObservation`.
- `app/process_email/service.py` — explicit content read, inbound validation, classification, projection and Operator Bridge preview orchestration.
- `app/process_email/api.py` — `POST /api/v1/process-email/preview` only.

### Existing production files modified

- `app/adapters/gmail_read/service.py` — use shared direction helpers without behavior change.
- `app/operator_bridge/models.py` — add optional typed semantic provenance to `OperatorObservation`.
- `app/operator_bridge/normalizer.py` — copy only allowlisted semantic provenance keys into `RelationshipEvent.metadata`.
- `app/main.py` — add process-email feature flag/service injection and route inclusion; no automatic OAuth/token construction.
- `.env.example` — add `OPPORTUNITY_PROCESS_EMAIL_ENABLED=false`.
- `README.md` — document explicit body-read/classification boundary only after implementation verification.
- `ROADMAP.md` — record classifier slice as implemented only after acceptance evidence exists.

### New tests

- `tests/test_gmail_read_direction.py`
- `tests/test_gmail_content_normalizer.py`
- `tests/test_gmail_content_provider.py`
- `tests/test_process_email_models.py`
- `tests/test_process_email_classifier.py`
- `tests/test_process_email_projector.py`
- `tests/test_process_email_service.py`
- `tests/test_api_process_email.py`
- `tests/test_process_email_privacy.py`
- `tests/test_process_email_release_contract.py`

### Existing tests modified

- `tests/test_gmail_read_service.py` — regression that shared direction helper preserves existing metadata-read semantics.
- `tests/test_operator_models.py` — typed provenance strictness and raw-text rejection.
- `tests/test_operator_normalizer.py` — allowlisted semantic provenance mapping only.
- `tests/test_operator_service.py` — stale-preview/idempotency remains unchanged with process-email provenance.

Do not modify Radar scoring, Search Health projection semantics, CV evidence authority, Outreach send gates, application preparation, target scoring or relationship state transition rules.

---

### Task 1: Extract Shared Gmail Direction Semantics Without Behavior Change

**Files:**
- Create: `app/adapters/gmail_read/direction.py`
- Create: `tests/test_gmail_read_direction.py`
- Modify: `app/adapters/gmail_read/service.py`
- Modify: `tests/test_gmail_read_service.py`

**Interfaces:**
- Produces: `normalize_owned_addresses(addresses) -> frozenset[str]`, `is_outbound(message, owned) -> bool`, `is_inbound(message, owned) -> bool`.
- Consumes: existing `GmailMessageEnvelope`.
- Later tasks use `is_inbound` for process-email selection; existing Gmail Read uses both helpers.

- [ ] **Step 1: Write failing direction tests**

Create `tests/test_gmail_read_direction.py` with explicit message constructors and these assertions:

```python
from datetime import datetime, timezone

from app.adapters.gmail_read.direction import is_inbound, is_outbound, normalize_owned_addresses
from app.adapters.gmail_read.models import GmailMessageEnvelope

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def message(*, sender: str, to: tuple[str, ...], labels: tuple[str, ...]) -> GmailMessageEnvelope:
    return GmailMessageEnvelope(
        message_id="m1",
        thread_id="t1",
        internal_date=NOW,
        label_ids=labels,
        from_address=sender,
        to_addresses=to,
    )


def test_owned_addresses_are_normalized_and_empty_set_is_rejected():
    assert normalize_owned_addresses({" OWNER@Example.Test "}) == frozenset({"owner@example.test"})


def test_inbound_requires_external_sender_and_owned_recipient():
    owned = frozenset({"owner@example.test"})
    assert is_inbound(message(sender="recruiter@example.test", to=("owner@example.test",), labels=("INBOX",)), owned)
    assert not is_inbound(message(sender="owner@example.test", to=("owner@example.test",), labels=("INBOX",)), owned)


def test_outbound_requires_sent_label_owned_sender_and_external_recipient():
    owned = frozenset({"owner@example.test"})
    assert is_outbound(message(sender="owner@example.test", to=("recruiter@example.test",), labels=("SENT",)), owned)
    assert not is_outbound(message(sender="owner@example.test", to=("owner@example.test",), labels=("SENT",)), owned)
```

Also assert `normalize_owned_addresses(set())` raises `ValueError("owned_addresses must contain at least one address")`.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_gmail_read_direction.py`

Expected: FAIL because `app.adapters.gmail_read.direction` does not exist.

- [ ] **Step 3: Implement shared helper**

Use this exact public shape:

```python
from collections.abc import Iterable

from app.adapters.gmail_read.models import GmailMessageEnvelope


def normalize_owned_addresses(addresses: Iterable[str]) -> frozenset[str]:
    normalized = frozenset(value.strip().lower() for value in addresses if value.strip())
    if not normalized:
        raise ValueError("owned_addresses must contain at least one address")
    return normalized


def _is_owned(address: str, owned: frozenset[str]) -> bool:
    return address.strip().lower() in owned


def _recipients(message: GmailMessageEnvelope) -> tuple[str, ...]:
    return (*message.to_addresses, *message.cc_addresses)


def is_outbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool:
    return (
        "SENT" in message.label_ids
        and _is_owned(message.from_address, owned)
        and any(not _is_owned(address, owned) for address in _recipients(message))
    )


def is_inbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool:
    return (
        not _is_owned(message.from_address, owned)
        and any(_is_owned(address, owned) for address in _recipients(message))
    )
```

Refactor `GmailReadService` to call `normalize_owned_addresses`, `is_outbound`, `is_inbound`; remove only the duplicated private direction helpers.

- [ ] **Step 4: Run focused GREEN plus regression**

```bash
pytest -q tests/test_gmail_read_direction.py tests/test_gmail_read_service.py tests/test_gmail_read_normalizer.py tests/test_gmail_read_provider.py tests/test_api_gmail_read.py
```

Expected: PASS with no change to current Gmail Read output.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/gmail_read/direction.py app/adapters/gmail_read/service.py tests/test_gmail_read_direction.py tests/test_gmail_read_service.py
git commit -m "refactor: share gmail direction semantics"
```

---

### Task 2: Add Explicit Gmail FULL Content Transport and Fail-Closed MIME Parser

**Files:**
- Create: `app/adapters/gmail_content/__init__.py`
- Create: `app/adapters/gmail_content/models.py`
- Create: `app/adapters/gmail_content/normalizer.py`
- Create: `app/adapters/gmail_content/provider.py`
- Create: `tests/test_gmail_content_normalizer.py`
- Create: `tests/test_gmail_content_provider.py`

**Interfaces:**
- Produces: `GmailContentEnvelope(message: GmailMessageEnvelope, current_message_text: str)`, `GmailContentError(code)`, protocol `GmailContentProvider.get_message_content(message_id) -> GmailContentEnvelope`, concrete `GmailRestContentProvider`.
- Consumes: existing metadata normalizer `normalize_message_payload(payload)` and `httpx.AsyncClient`.
- No thread/list API is exposed.

- [ ] **Step 1: Write RED parser tests with concrete Gmail payloads**

Create helpers that base64url-encode UTF-8 fixture text without padding:

```python
import base64


def b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")
```

Test all of these cases in `tests/test_gmail_content_normalizer.py`:

1. nested multipart chooses `text/plain` over HTML;
2. HTML-only message becomes visible text and removes `<script>`/`<style>` content;
3. parts with non-empty `filename` or `Content-Disposition: attachment` are ignored even when MIME type is text;
4. quoted block beginning with `On ... wrote:`, `El ... escribió:` or `-----Original Message-----` is excluded from `current_message_text`;
5. standard signature delimiter line `-- ` removes following signature text;
6. invalid base64url returns `GmailContentError("gmail_payload_invalid")`;
7. no usable plain/HTML body returns `missing_usable_body`;
8. body-only quoted history with no usable current text returns `quoted_content_ambiguous`;
9. decoded candidate text above `256 * 1024` bytes returns `content_too_large` instead of truncating.

Example happy-path fixture:

```python
payload = {
    "id": "m1",
    "threadId": "t1",
    "internalDate": "1788264000000",
    "labelIds": ["INBOX"],
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "recruiter@example.test"},
            {"name": "To", "value": "owner@example.test"},
            {"name": "Subject", "value": "Interview"},
        ],
        "parts": [
            {"mimeType": "text/plain", "filename": "", "body": {"data": b64url("We would like to invite you to an interview.")}},
            {"mimeType": "text/html", "filename": "", "body": {"data": b64url("<p>HTML fallback</p>")}},
        ],
    },
}
```

- [ ] **Step 2: Run parser RED**

Run: `pytest -q tests/test_gmail_content_normalizer.py`

Expected: FAIL because the package does not exist.

- [ ] **Step 3: Implement strict transient contracts**

`app/adapters/gmail_content/models.py`:

```python
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.gmail_read.models import GmailMessageEnvelope

MAX_MESSAGE_TEXT_BYTES = 256 * 1024


class StrictGmailContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GmailContentEnvelope(StrictGmailContentModel):
    message: GmailMessageEnvelope
    current_message_text: str = Field(min_length=1)


class GmailContentError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
```

Do not add fields for raw MIME, body HTML, snippet, provider payload or attachment data.

- [ ] **Step 4: Implement recursive MIME extraction with stdlib only**

`normalize_full_message_payload(payload)` first calls existing `normalize_message_payload(payload)` for metadata. Recursively traverse dict/list `parts`; a candidate part is accepted only when `filename` is empty, attachment disposition is absent, and `mimeType` is `text/plain` or `text/html`.

Use base64url padding repair:

```python
padding = "=" * (-len(data) % 4)
raw = base64.urlsafe_b64decode(data + padding)
text = raw.decode("utf-8", errors="strict")
```

For HTML fallback, implement a small `HTMLParser` subclass that ignores data while inside `script` or `style`, inserts separators for block tags (`p`, `div`, `br`, `li`, `tr`) and applies `html.unescape` through parser callbacks. Do not add BeautifulSoup or another dependency.

Quote stripping uses only explicit markers:

```python
_QUOTE_MARKERS = (
    re.compile(r"(?im)^On .+ wrote:\s*$"),
    re.compile(r"(?im)^El .+ escribió:\s*$"),
    re.compile(r"(?im)^-----Original Message-----\s*$"),
)
```

Take text before the earliest known marker, then remove content after a standalone `-- ` signature delimiter. Normalize internal whitespace line-by-line without joining all sentences into one line. If the remaining text is empty, raise `quoted_content_ambiguous`.

Apply the 256 KiB bound to UTF-8 encoded normalized current text before returning.

- [ ] **Step 5: Run parser GREEN**

Run: `pytest -q tests/test_gmail_content_normalizer.py`

Expected: PASS.

- [ ] **Step 6: Write RED provider tests**

`tests/test_gmail_content_provider.py` must prove:

```python
request.url.path == "/gmail/v1/users/me/messages/m1"
request.url.params["format"] == "full"
```

and that there is exactly one GET. Assert the provider has no `get_thread`, list or search method. Test 401/403/404/429/timeout mappings using the same bounded codes as Gmail Read and ensure access token/provider response body never appears in exception text.

- [ ] **Step 7: Implement single-message provider**

Public protocol:

```python
class GmailContentProvider(Protocol):
    async def get_message_content(self, message_id: str) -> GmailContentEnvelope: ...
```

Concrete provider requests only `messages/{quoted_id}` with `params={"format": "full"}`. Reuse the same HTTP status mapping semantics as Gmail Read but keep this as a separate provider class so metadata reads cannot accidentally widen to FULL.

- [ ] **Step 8: Run transport GREEN and commit**

```bash
pytest -q tests/test_gmail_content_normalizer.py tests/test_gmail_content_provider.py tests/test_gmail_read_provider.py
python -m compileall -q app/adapters/gmail_content
```

Expected: PASS.

```bash
git add app/adapters/gmail_content tests/test_gmail_content_normalizer.py tests/test_gmail_content_provider.py
git commit -m "feat: add explicit gmail content reader"
```

---

### Task 3: Define Process Email Contracts and Stable Classifier Interface

**Files:**
- Create: `app/process_email/__init__.py`
- Create: `app/process_email/models.py`
- Create: `app/process_email/classifier.py`
- Create: `tests/test_process_email_models.py`

**Interfaces:**
- Produces exact literals/types: `ProcessSignalKind`, `ProcessConfidence`, `ClassificationDisposition`, `ProcessEmailStatus`, `EvidenceSpan`, `ProcessSignal`, `ProcessClassification`, `ProcessEmailSelection`, `ProcessProjection`, `ProcessEmailPreview`, `ProcessClassifier`.
- Consumes: `OperatorObservation`, `ObservationPreview`, timezone-aware `datetime`.

- [ ] **Step 1: Write RED strict-model tests**

Test exact literals, strict extra rejection, exactly one non-empty `message_id`, timezone-aware `observed_at`, `external_actions=[]`, and invariant that `operator_preview` is only present when `proposed_observation` is present.

Use these exact public literals:

```python
ProcessSignalKind = Literal[
    "APPLICATION_ACKNOWLEDGED",
    "INTERVIEW_PROPOSED",
    "STAGE_ADVANCED",
    "PROCESS_UPDATED",
    "OFFER_RECEIVED",
    "REJECTED",
]
ProcessConfidence = Literal["HIGH", "MEDIUM", "LOW"]
ClassificationDisposition = Literal["CLASSIFIED", "NOT_PROCESS", "AMBIGUOUS"]
ProcessEmailStatus = Literal[
    "CLASSIFIED",
    "NOT_PROCESS",
    "AMBIGUOUS",
    "CONTENT_UNAVAILABLE",
    "PROVIDER_ERROR",
    "INVALID_SELECTION",
    "BLOCKED",
]
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_process_email_models.py`

Expected: FAIL because `app.process_email` does not exist.

- [ ] **Step 3: Implement strict contracts**

Use `ConfigDict(extra="forbid")`. The key models are:

```python
class EvidenceSpan(StrictProcessEmailModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_range(self):
        if self.end <= self.start:
            raise ValueError("evidence span end must be after start")
        return self


class ProcessSignal(StrictProcessEmailModel):
    kind: ProcessSignalKind
    confidence: ProcessConfidence
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list, min_length=1)


class ProcessClassification(StrictProcessEmailModel):
    disposition: ClassificationDisposition
    classifier_version: Literal["deterministic-process-email-v1"]
    ruleset_version: Literal["es-en-2026-09-v1"]
    signals: list[ProcessSignal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

Validator rules:
- `CLASSIFIED` requires at least one signal;
- `NOT_PROCESS` and `AMBIGUOUS` require `signals=[]` only when there is no retained positive evidence; conflicting positive evidence may be returned separately by service as `AMBIGUOUS` with sanitized conflict warning, but do not serialize the conflicting raw text outside transient signal evidence;
- `external_actions` in `ProcessEmailPreview` must always be empty.

`ProcessEmailSelection` fields are exactly `account_id`, optional `contact_id`, `message_id`, `selected_by`.

`ProcessEmailPreview` fields are exactly: `status`, `classifier_version`, `ruleset_version`, `source_ref`, `observed_at`, `signals`, `warnings`, optional `proposed_observation`, optional `operator_preview`, `external_actions`.

- [ ] **Step 4: Add classifier protocol**

```python
from typing import Protocol

from app.process_email.models import ProcessClassification


class ProcessClassifier(Protocol):
    def classify(self, text: str) -> ProcessClassification: ...
```

No provider, DB or HTTP dependency belongs in this protocol.

- [ ] **Step 5: Run GREEN and commit**

```bash
pytest -q tests/test_process_email_models.py
python -m compileall -q app/process_email
```

Expected: PASS.

```bash
git add app/process_email/__init__.py app/process_email/models.py app/process_email/classifier.py tests/test_process_email_models.py
git commit -m "feat: add process email classification contracts"
```

---

### Task 4: Implement Deterministic ES/EN Lifecycle Classification

**Files:**
- Create: `app/process_email/deterministic.py`
- Create: `tests/test_process_email_classifier.py`

**Interfaces:**
- Consumes: normalized current-message `str` only.
- Produces: `ProcessClassification` using `classifier_version="deterministic-process-email-v1"`, `ruleset_version="es-en-2026-09-v1"`.
- No network, filesystem, DB, clock or LLM dependency.

- [ ] **Step 1: Write RED semantic corpus**

Use a table-driven bilingual corpus. Minimum explicit HIGH examples:

```text
APPLICATION_ACKNOWLEDGED
EN: "We received your application for the role."
EN: "Thank you for applying."
ES: "Hemos recibido tu candidatura."
ES: "Gracias por postularte."

INTERVIEW_PROPOSED
EN: "We would like to invite you to an interview."
EN: "We'd like to schedule an interview with you."
ES: "Queremos invitarte a una entrevista."
ES: "Nos gustaría coordinar una entrevista con vos."

STAGE_ADVANCED
EN: "You have advanced to the next stage of our hiring process."
EN: "We would like to move you forward to the technical interview."
ES: "Avanzaste a la siguiente etapa del proceso."
ES: "Queremos que avances a la entrevista técnica."

PROCESS_UPDATED
EN: "We need to reschedule your interview to Thursday."
EN: "The hiring process is taking longer than expected and remains under review."
ES: "Necesitamos reprogramar tu entrevista para el jueves."
ES: "El proceso está demorando más de lo previsto y sigue en revisión."

OFFER_RECEIVED
EN: "We are pleased to offer you the position."
EN: "We would like to extend you an offer."
ES: "Nos complace ofrecerte el puesto."
ES: "Queremos hacerte una oferta laboral."

REJECTED
EN: "We will not be moving forward with your application."
EN: "We decided to move forward with another candidate."
ES: "No continuaremos con tu candidatura."
ES: "Hemos decidido avanzar con otros perfiles."
```

Minimum negative/guard regressions:

```text
"Our interview process normally takes two weeks." -> no INTERVIEW_PROPOSED
"If selected, you may be invited to interview." -> no INTERVIEW_PROPOSED
"We are not yet scheduling interviews." -> no INTERVIEW_PROPOSED
"The compensation range for this role is USD 80k-100k." -> no OFFER_RECEIVED
"We are still reviewing applications." -> no REJECTED
"Aún no tomamos una decisión." -> no REJECTED
```

Explicit LOW examples map to `PROCESS_UPDATED` LOW with `low_confidence_only` and zero mutation in later projection:

```text
"We will share next steps soon."
"Tenemos novedades sobre tu perfil."
```

Explicit `NOT_PROCESS` examples are current-message facts that clearly do not express a lifecycle event:

```text
"Automatic reply: I am out of the office until Monday."
"Respuesta automática: estoy fuera de la oficina hasta el lunes."
```

Unknown generic text such as `"Hello, thanks for your message."` returns `AMBIGUOUS`, not `NOT_PROCESS`.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_process_email_classifier.py`

Expected: FAIL because deterministic classifier does not exist.

- [ ] **Step 3: Implement explicit rule tables and span extraction**

Use compiled regex rules with fixed reason codes. Keep rule declarations data-only and bounded. Required reason codes:

```text
APPLICATION_RECEIPT_EXPLICIT
INTERVIEW_INVITATION_EXPLICIT
INTERVIEW_SCHEDULING_CONTEXT
STAGE_ADVANCEMENT_EXPLICIT
PROCESS_RESCHEDULE_EXPLICIT
PROCESS_DELAY_EXPLICIT
OFFER_EXPLICIT
REJECTION_EXPLICIT
GENERIC_PROCESS_SIGNAL
OUT_OF_OFFICE_EXPLICIT
```

Each matched positive rule returns `EvidenceSpan(match.start(), match.end(), match.group(0))` from transient normalized text.

Implement guard patterns before positive interview/offer/rejection promotion. At minimum:

```python
_HYPOTHETICAL = [
    re.compile(r"\bif selected\b", re.I),
    re.compile(r"\bmay be invited\b", re.I),
    re.compile(r"\bsi (?:sos|eres|resultas) seleccionad[oa]\b", re.I),
    re.compile(r"\bpodr[ií]as? ser invitad[oa]\b", re.I),
]
_NEGATED_INTERVIEW = [
    re.compile(r"\bnot yet scheduling interviews\b", re.I),
    re.compile(r"\ba[uú]n no (?:estamos )?coordinando entrevistas\b", re.I),
]
_GENERIC_PROCESS_DESCRIPTION = [
    re.compile(r"\bour interview process normally\b", re.I),
    re.compile(r"\bnuestro proceso de entrevistas normalmente\b", re.I),
]
```

Do not use one bare keyword as sufficient evidence.

- [ ] **Step 4: Implement multi-signal retention and conflict disposition**

Collect compatible signals deterministically in source-text order, then stable tie-break by signal priority:

```text
OFFER_RECEIVED > STAGE_ADVANCED > INTERVIEW_PROPOSED > PROCESS_UPDATED > APPLICATION_ACKNOWLEDGED
```

If `REJECTED` coexists with any of `INTERVIEW_PROPOSED`, `STAGE_ADVANCED`, `PROCESS_UPDATED`, `OFFER_RECEIVED`, return `AMBIGUOUS`, no mutation-driving selection, warning `conflicting_process_signals`. Keep evidence only in the transient response object; nothing from this classifier persists by itself.

If no positive rule matched:
- explicit out-of-office pattern -> `NOT_PROCESS`;
- otherwise -> `AMBIGUOUS`.

- [ ] **Step 5: Run GREEN and determinism regression**

```bash
pytest -q tests/test_process_email_classifier.py
pytest -q tests/test_process_email_classifier.py -x
```

Add a test that two calls with the same string produce model-equal results and identical JSON.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/process_email/deterministic.py tests/test_process_email_classifier.py
git commit -m "feat: classify hiring process email signals"
```

---

### Task 5: Add Typed Semantic Provenance and Relationship-Aware Projection

**Files:**
- Modify: `app/operator_bridge/models.py`
- Modify: `app/operator_bridge/normalizer.py`
- Modify: `tests/test_operator_models.py`
- Modify: `tests/test_operator_normalizer.py`
- Create: `app/process_email/projector.py`
- Create: `tests/test_process_email_projector.py`

**Interfaces:**
- Produces: optional `ObservationSemanticProvenance` on `OperatorObservation`; `ProcessEventProjector.project(...) -> ProcessProjection`.
- Consumes: `ProcessClassification`, current `RelationshipAccount | None`, selection/account identifiers and message timestamp.
- Existing observations with `semantic_provenance=None` remain semantically identical.

- [ ] **Step 1: Write RED typed provenance tests**

Extend `tests/test_operator_models.py`:

```python
from app.operator_bridge.models import ObservationSemanticProvenance


def test_semantic_provenance_is_typed_and_rejects_source_text():
    provenance = ObservationSemanticProvenance(
        producer="PROCESS_EMAIL_CLASSIFIER",
        producer_version="deterministic-process-email-v1",
        policy_version="es-en-2026-09-v1",
        classification="INTERVIEW_PROPOSED",
        reason_code="INTERVIEW_INVITATION_EXPLICIT",
    )
    assert provenance.producer == "PROCESS_EMAIL_CLASSIFIER"

    with pytest.raises(ValidationError):
        ObservationSemanticProvenance(
            producer="PROCESS_EMAIL_CLASSIFIER",
            producer_version="deterministic-process-email-v1",
            policy_version="es-en-2026-09-v1",
            classification="INTERVIEW_PROPOSED",
            reason_code="INTERVIEW_INVITATION_EXPLICIT",
            evidence_text="private recruiter sentence",
        )
```

Also prove existing `_observation()` still validates without provenance and raw `body`, `subject`, arbitrary metadata remain rejected.

- [ ] **Step 2: Run provenance RED**

Run: `pytest -q tests/test_operator_models.py`

Expected: FAIL on missing `ObservationSemanticProvenance`.

- [ ] **Step 3: Implement bounded provenance model**

Add:

```python
class ObservationSemanticProvenance(StrictOperatorModel):
    producer: Literal["PROCESS_EMAIL_CLASSIFIER"]
    producer_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    policy_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    classification: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    reason_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
```

and on `OperatorObservation`:

```python
semantic_provenance: ObservationSemanticProvenance | None = None
```

Do not add generic `metadata: dict` or free-form provenance.

- [ ] **Step 4: Write RED normalizer allowlist test**

Extend `tests/test_operator_normalizer.py` so a process observation with provenance produces exactly these additional keys:

```text
semantic_producer
semantic_producer_version
semantic_policy_version
semantic_classification
semantic_reason_code
```

and no `body`, `subject`, `evidence`, `text` key.

- [ ] **Step 5: Implement normalizer mapping**

Only when `semantic_provenance is not None`:

```python
metadata.update({
    "semantic_producer": provenance.producer,
    "semantic_producer_version": provenance.producer_version,
    "semantic_policy_version": provenance.policy_version,
    "semantic_classification": provenance.classification,
    "semantic_reason_code": provenance.reason_code,
})
```

Existing event ID remains based on source identity; observation hash naturally includes the typed provenance and therefore protects semantic equality.

- [ ] **Step 6: Run operator GREEN**

```bash
pytest -q tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_operator_service.py tests/test_api_operator_bridge.py
```

Expected: PASS.

- [ ] **Step 7: Write RED projector transition matrix**

Create `tests/test_process_email_projector.py` covering the full table:

```text
ACK + closed -> none
ACK + open -> none
INTERVIEW + closed -> PROCESS_OPENED
INTERVIEW + open -> PROCESS_UPDATED
STAGE_ADVANCED + closed -> PROCESS_OPENED
STAGE_ADVANCED + open -> PROCESS_UPDATED
PROCESS_UPDATED + closed -> none + no_open_process_to_update
PROCESS_UPDATED + open -> PROCESS_UPDATED
OFFER + closed -> PROCESS_OPENED
OFFER + open -> PROCESS_UPDATED
REJECTED + closed -> none + no_open_process_to_close
REJECTED + open -> PROCESS_CLOSED
LOW-only -> none + low_confidence_only
AMBIGUOUS -> none
```

Assert generated observation identity is:

```text
gmail-message:m1:process-signal:INTERVIEW_PROPOSED
```

for the mutation-driving signal and is independent of classifier/ruleset version.

- [ ] **Step 8: Implement projector**

Public method:

```python
class ProcessEventProjector:
    def project(
        self,
        *,
        classification: ProcessClassification,
        account: RelationshipAccount | None,
        account_id: str,
        contact_id: str | None,
        message_id: str,
        observed_at: datetime,
    ) -> ProcessProjection: ...
```

If an account is required for mutation and is `None`, return no observation with `unknown_relationship_account` so service can expose `BLOCKED`.

Select only HIGH/MEDIUM signals for mutation. Resolve compatible positive priority exactly as in Global Constraints. Create normalized reasons:

```python
_REASON = {
    "INTERVIEW_PROPOSED": "explicit interview invitation observed",
    "STAGE_ADVANCED": "explicit hiring-stage advancement observed",
    "PROCESS_UPDATED": "explicit hiring-process update observed",
    "OFFER_RECEIVED": "explicit employment offer observed",
    "REJECTED": "explicit process rejection observed",
}
```

Build `OperatorObservation` with `source_type="EMAIL_PROVIDER"`, `source_name="gmail"`, `source_ref=f"gmail:message:{message_id}"`, no `process_label`, and typed semantic provenance from the mutation-driving signal/rule.

- [ ] **Step 9: Run projector GREEN and commit**

```bash
pytest -q tests/test_process_email_projector.py tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_operator_service.py
```

Expected: PASS.

```bash
git add app/operator_bridge/models.py app/operator_bridge/normalizer.py app/process_email/projector.py tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_process_email_projector.py
git commit -m "feat: project classified process facts safely"
```

---

### Task 6: Orchestrate Explicit Read -> Classification -> Operator Preview

**Files:**
- Create: `app/process_email/service.py`
- Create: `tests/test_process_email_service.py`

**Interfaces:**
- Consumes: `GmailContentProvider`, owned addresses, `ProcessClassifier`, `ProcessEventProjector`, `SQLiteRelationshipRepository | None`, `OperatorBridgeService | None`.
- Produces: `ProcessEmailService.preview(selection) -> ProcessEmailPreview`.
- No direct relationship write method exists.

- [ ] **Step 1: Write RED service tests with fakes**

Use a `FakeContentProvider` that records requested IDs and returns one `GmailContentEnvelope`. Test:

1. exactly one selected `message_id` is requested;
2. inbound interview returns `CLASSIFIED`, transient evidence, one `PROCESS_OPENED` candidate and an `IMPORTABLE` existing operator preview;
3. outbound/self-authored message returns `INVALID_SELECTION`, `message_not_inbound`, zero classifier call and zero candidate;
4. ACK-only returns `CLASSIFIED`, no candidate, no DB write;
5. unknown relationship account only blocks when a mutation candidate would otherwise be needed;
6. LOW-only, rejection-without-open-process, generic update-without-open-process and conflicting signals return zero candidate;
7. provider `gmail_rate_limited` maps to `PROVIDER_ERROR` without leaking provider payload;
8. `content_too_large`, `missing_usable_body`, `quoted_content_ambiguous`, `unsupported_mime` map to `CONTENT_UNAVAILABLE`;
9. `operator_bridge=None` with a mutation candidate returns `BLOCKED` + `operator_bridge_unavailable`;
10. service call leaves `relationship_events` unchanged.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_process_email_service.py`

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement service constructor and owned-address normalization**

```python
class ProcessEmailService:
    def __init__(
        self,
        content_provider: GmailContentProvider,
        classifier: ProcessClassifier,
        projector: ProcessEventProjector,
        *,
        owned_addresses: set[str] | frozenset[str],
        relationship_repository: SQLiteRelationshipRepository | None,
        operator_bridge: OperatorBridgeService | None,
    ) -> None:
        self.content_provider = content_provider
        self.classifier = classifier
        self.projector = projector
        self.owned_addresses = normalize_owned_addresses(owned_addresses)
        self.relationship_repository = relationship_repository
        self.operator_bridge = operator_bridge
```

- [ ] **Step 4: Implement preview orchestration in fail-closed order**

Order is contractual:

```text
fetch selected content
-> validate inbound
-> classify transient current_message_text
-> if semantic disposition is non-mutating, return response
-> read current relationship account
-> projector derives zero/one candidate
-> if no candidate, return response with warnings
-> require Operator Bridge
-> call bridge.preview(candidate)
-> return candidate + existing ObservationPreview
```

Never call `import_observation` from this service.

For all successful classifications, `source_ref=f"gmail:message:{message_id}"` and `observed_at=message.internal_date`. Return `classifier_version`/`ruleset_version` even on `NOT_PROCESS`/`AMBIGUOUS`; infrastructure errors may use the canonical versions from the configured deterministic classifier.

- [ ] **Step 5: Add no-sensitive-logging guard**

The module must not log `current_message_text`, subject, evidence spans or entire `ProcessEmailPreview`. If logging is needed for bounded errors, log only static error codes and provider name. Add a test using `caplog` with sentinel private body/subject strings and assert neither appears.

- [ ] **Step 6: Run GREEN and commit**

```bash
pytest -q tests/test_process_email_service.py tests/test_process_email_projector.py tests/test_process_email_classifier.py
```

Expected: PASS.

```bash
git add app/process_email/service.py tests/test_process_email_service.py
git commit -m "feat: preview classified process emails"
```

---

### Task 7: Add Process Email API and Independent Feature Flag

**Files:**
- Create: `app/process_email/api.py`
- Create: `tests/test_api_process_email.py`
- Modify: `app/main.py`
- Modify: `.env.example`

**Interfaces:**
- Produces one route: `POST /api/v1/process-email/preview`.
- `create_app(...)` gains `process_email_service: ProcessEmailService | None = None` and `enable_process_email: bool | None = None`.
- No process-email import route exists.

- [ ] **Step 1: Write RED API boundary tests**

Mirror existing Gmail Read route tests. Prove:

```python
assert "/api/v1/process-email/preview" not in create_app(...).openapi()["paths"]
```

by default.

When `enable_process_email=True` and no injected service, POST returns exactly:

```json
{"detail":"process_email_unavailable"}
```

with status 503.

With a fake injected service, request JSON is exactly:

```json
{
  "account_id": "example-co",
  "contact_id": "contact-1",
  "message_id": "m1",
  "selected_by": "operator"
}
```

and response carries `external_actions: []`.

Assert OpenAPI contains no `/api/v1/process-email/import` path.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_api_process_email.py`

Expected: FAIL because route/wiring does not exist.

- [ ] **Step 3: Implement API router**

```python
def create_process_email_router(service: ProcessEmailService | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/process-email")

    @router.post("/preview", response_model=ProcessEmailPreview)
    async def preview(selection: ProcessEmailSelection) -> ProcessEmailPreview:
        if service is None:
            raise HTTPException(status_code=503, detail="process_email_unavailable")
        return await service.preview(selection)

    return router
```

No logging middleware or raw-request logging is added.

- [ ] **Step 4: Add independent boolean flag in `app/main.py`**

Add `_process_email_enabled()` using the same strict boolean parser shape as `_gmail_read_enabled()`, reading only `OPPORTUNITY_PROCESS_EMAIL_ENABLED` with default `false`.

Add parameters:

```python
process_email_service: ProcessEmailService | None = None,
enable_process_email: bool | None = None,
```

and include router only when enabled:

```python
if process_email_enabled:
    api.include_router(create_process_email_router(process_email_service))
```

Do not construct access tokens, OAuth clients, Gmail FULL providers or a relationship DB automatically here. Injection remains explicit, matching the current Gmail Read boundary.

- [ ] **Step 5: Update `.env.example`**

Append exactly:

```text
OPPORTUNITY_PROCESS_EMAIL_ENABLED=false
```

Do not add token/credential examples.

- [ ] **Step 6: Run API GREEN and regression suite**

```bash
pytest -q tests/test_api_process_email.py tests/test_api_gmail_read.py tests/test_api_operator_bridge.py
python -m compileall -q app/main.py app/process_email
```

Expected: PASS; Gmail Read and Operator Bridge route presence defaults remain unchanged.

- [ ] **Step 7: Commit**

```bash
git add app/process_email/api.py app/main.py .env.example tests/test_api_process_email.py
git commit -m "feat: expose process email preview route"
```

---

### Task 8: End-to-End Privacy, Confirmation and Semantic Regression Harness

**Files:**
- Create: `tests/test_process_email_privacy.py`
- Modify as needed only to fix failures uncovered by this task: focused files from Tasks 2-7.

**Interfaces:**
- Proves full flow: Gmail FULL fixture -> transient classification -> candidate -> existing preview -> explicit existing import -> persisted `RelationshipEvent`.
- Proves no hidden persistence before import and no sensitive text after import.

- [ ] **Step 1: Write RED end-to-end interview test**

Build a real temporary `SQLiteRelationshipRepository`, register `example-co`, construct `OperatorBridgeService`, a fake content provider returning:

```text
subject sentinel: PRIVATE SUBJECT SENTINEL
body sentinel: We would like to invite you to an interview. PRIVATE BODY SENTINEL
```

Call `ProcessEmailService.preview`. Before confirmation assert:

```python
assert repo.list_events("example-co") == []
assert preview.proposed_observation is not None
assert preview.operator_preview is not None
assert preview.operator_preview.status == "IMPORTABLE"
```

Then explicitly call existing bridge import with the returned candidate and preview hash. Assert one `PROCESS_OPENED` event exists.

- [ ] **Step 2: Assert persistence contains only allowlisted machine provenance**

Serialize all stored relationship rows/events available through repository APIs and raw SQLite `payload_json`. Assert none contains:

```text
PRIVATE SUBJECT SENTINEL
PRIVATE BODY SENTINEL
invite you to an interview
<html
script
```

Assert event metadata includes exactly the existing operator keys plus these semantic keys:

```text
semantic_producer=PROCESS_EMAIL_CLASSIFIER
semantic_producer_version=deterministic-process-email-v1
semantic_policy_version=es-en-2026-09-v1
semantic_classification=INTERVIEW_PROPOSED
semantic_reason_code=INTERVIEW_INVITATION_EXPLICIT
```

- [ ] **Step 3: Add required semantic regressions end-to-end**

Prove each ends with zero persisted event unless explicitly described otherwise:

- ATS receipt -> no `PROCESS_OPENED`;
- outbound operator email -> `INVALID_SELECTION`;
- rejection without open process -> no fabricated event;
- quoted old interview under current rejection -> only current rejection may drive closure when a process is open;
- compensation-range text -> no `OFFER_RECEIVED`;
- hypothetical interview -> no candidate;
- LOW-only -> no candidate;
- conflicting rejection + interview -> `AMBIGUOUS`, no candidate.

- [ ] **Step 4: Add stale-preview regression using real bridge**

Generate an interview preview, mutate relationship state with a different valid event before import, then submit the old process-email observation/hash through `OperatorBridgeService.import_observation`. Expected: `BLOCKED_STALE_PREVIEW` and no process-email event appended.

- [ ] **Step 5: Add exact retry/idempotency regression**

Import an accepted process-email observation, then repeat identical import. Expected second result `ALREADY_IMPORTED`, one relationship event total for that observation identity.

- [ ] **Step 6: Run privacy/integration GREEN**

```bash
pytest -q tests/test_process_email_privacy.py tests/test_process_email_service.py tests/test_operator_service.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_process_email_privacy.py app/adapters/gmail_content app/process_email app/operator_bridge
git commit -m "test: prove process email privacy boundaries"
```

Only include production files in this commit if a RED regression from this task required a minimal fix.

---

### Task 9: Public Documentation and Release Contract

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Create: `tests/test_process_email_release_contract.py`

**Interfaces:**
- Produces accurate public contract; no real email bodies, personal metric values or provider IDs.

- [ ] **Step 1: Write RED release-contract test**

Read README/ROADMAP and require these exact concepts to appear:

```text
Process Email
selected inbound message
body access != body persistence
classification != authority
APPLICATION_ACKNOWLEDGED
OPPORTUNITY_PROCESS_EMAIL_ENABLED=false
human confirmation
```

Also assert docs do not claim mailbox-wide sync, automatic process mutation, automatic follow-up or external LLM classification.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_process_email_release_contract.py`

Expected: FAIL until docs describe the implemented slice.

- [ ] **Step 3: Update README**

Add a concise section next to Gmail Read / Operator Bridge showing:

```text
explicit inbound Gmail message
-> transient FULL content
-> deterministic ES/EN signals + evidence preview
-> zero/one candidate OperatorObservation
-> existing Operator Bridge preview
-> explicit human confirm/import
```

State that body/subject/evidence spans are transient, no attachments/threads/mailbox scan are classified, and `APPLICATION_ACKNOWLEDGED` is not a process open.

- [ ] **Step 4: Update ROADMAP**

Move Process-email classifier from AFTER to an implemented V0.2E-adjacent slice only after Tasks 1-8 pass. Keep WhatsApp/conversation-provider work separate and future. Do not imply Search Health offer metrics exist yet.

- [ ] **Step 5: Run GREEN and commit**

```bash
pytest -q tests/test_process_email_release_contract.py
git add README.md ROADMAP.md tests/test_process_email_release_contract.py
git commit -m "docs: document process email classifier"
```

Expected: PASS.

---

### Task 10: Full Verification, Review and PR Gate

**Files:** no new behavior unless verification exposes a bug; every behavioral fix begins with a RED regression in the narrowest relevant test.

**Interfaces:** implementation branch -> reviewed PR -> `main`.

- [ ] **Step 1: Run full local verification**

```bash
python -m pytest -q
python -m compileall -q app tests
git diff --check main...HEAD
```

Expected: all tests PASS, compile PASS, whitespace clean. Baseline before this feature was 619 passing tests; the final total must be greater and have zero failures.

- [ ] **Step 2: Run explicit scope/privacy checks**

```bash
git diff --name-only main...HEAD
git grep -n -E 'mailbox.*sync|auto.*send|auto.*follow.?up' -- app/process_email app/adapters/gmail_content || true
git grep -n -E 'body|subject|evidence_span' -- app/operator_bridge || true
```

Manually verify any `body|subject|evidence_span` hits in Operator Bridge are tests/comments only; production `OperatorObservation` and `RelationshipEvent.metadata` must have no raw-text field.

Run:

```bash
git ls-files -- '*.local.*' 'state/*.sqlite3*' 'artifacts/**'
```

Expected: no newly tracked private runtime evidence attributable to this feature.

- [ ] **Step 3: Verify existing Gmail metadata contract explicitly**

```bash
pytest -q tests/test_gmail_read_provider.py::test_get_message_uses_metadata_read_endpoint_and_bearer_token \
  tests/test_gmail_read_provider.py::test_get_thread_uses_metadata_read_endpoint
```

Expected: PASS and requests still use `format=metadata`.

- [ ] **Step 4: Inspect implementation diff against spec**

Reviewer checklist:

```text
one message only
inbound only
FULL content only in gmail_content
256 KiB fail-closed bound
attachments excluded
ES/EN deterministic rules
LOW/ambiguous/conflict zero mutation
ACK != process open
rejection without open process != fabricated close
typed provenance only
zero direct Relationship Memory writes
no process-email import endpoint
feature flag separate and default false
no new runtime dependency
no external LLM
no sensitive content persistence/logging
```

- [ ] **Step 5: Open implementation PR**

Title:

```text
feat: add evidence-aware process email classifier
```

PR body must state the content-read/privacy boundary, deterministic classifier versions, exact transition rules, human-confirmation requirement, no mailbox sync, no external LLM, no new runtime dependency, full test/compile/diff evidence, and any review regressions discovered during implementation.

- [ ] **Step 6: Require CI on exact PR head**

Require the repository's existing tests workflow to complete successfully on the exact current head, including pytest, compile, diff/private-file guard, recruiter preview generation, SHA-bound offline runtime build and Python 3.12/3.13 offline verification. This feature must not weaken those jobs.

- [ ] **Step 7: Resolve findings with TDD**

For every correctness/privacy finding:

```text
write narrow failing regression
-> prove RED
-> minimal implementation fix
-> focused GREEN
-> full suite
-> inspect diff
-> commit
```

Do not merge with unresolved privacy, lifecycle or stale-preview findings.

- [ ] **Step 8: Merge only the exact verified head**

After merge, verify the PR is `merged=true`, inspect `main` merge commit, and verify the post-merge workflow on that merge commit before declaring Process Email V1 complete.

---

## Plan Self-Review

- **Spec coverage:** explicit inbound selection, separate FULL transport, MIME/base64/HTML handling, quote/signature separation, 256 KiB guard, signal/disposition taxonomy, confidence, deterministic ES/EN rules, multi-signal conflict behavior, relationship-state projection, response-only non-mutating evidence, typed provenance, API/feature flag, existing confirmation boundary, privacy regressions, docs and CI all map to tasks.
- **Placeholder scan:** no undefined implementation step remains; every code-producing task specifies concrete files, public signatures, literals, error codes and focused commands.
- **Type consistency:** `GmailContentEnvelope` is defined in Task 2; process contracts and `ProcessClassifier` in Task 3; deterministic classifier in Task 4; `ObservationSemanticProvenance` and `ProcessEventProjector` in Task 5; `ProcessEmailService` in Task 6; API consumes the same `ProcessEmailSelection`/`ProcessEmailPreview` in Task 7.
- **Dependency direction:** Gmail transport does not know lifecycle semantics; classifier has no provider/DB dependency; projector owns semantic-to-domain mapping; service orchestrates but does not import; Operator Bridge remains the only write boundary.
- **YAGNI:** no thread classifier, mailbox scan, background worker, attachments, link crawling, salary extraction, role extraction, sentiment, success prediction, classification ledger, Search Health schema change, CLI or LLM backend is implemented.
- **Privacy:** raw content exists only in `GmailContentEnvelope`/transient evidence models and tests; persisted provenance is bounded machine-generated identifiers only.
- **TDD:** each behavior task starts with RED, proves the failure, implements the minimum contract, runs focused GREEN and commits before the next boundary.
