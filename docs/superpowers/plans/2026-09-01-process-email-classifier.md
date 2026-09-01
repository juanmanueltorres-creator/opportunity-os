# Process Email Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, deterministic ES/EN process-email classifier for one explicitly selected inbound Gmail message, show transient evidence in preview, derive at most one candidate process observation, and keep the existing Operator Bridge as the only confirmed write path into Relationship Memory.

**Architecture:** Preserve the existing metadata-only Gmail adapter and add a separate `gmail_content` transport for explicit FULL-message reads. A new `process_email` package owns typed classification, deterministic rules, relationship-aware event projection and preview orchestration; raw email text remains request-local. When a mutation is defensible, the service creates one typed `OperatorObservation`, asks the existing Operator Bridge for the state-transition preview, and leaves confirmation/import to the existing `/api/v1/operator/observations/import` endpoint.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, `httpx`, stdlib `base64`, stdlib `html.parser`, stdlib `re`, pytest/pytest-asyncio. No new runtime dependency and no external LLM call in V1.

**Spec:** `docs/superpowers/specs/2026-09-01-process-email-classifier-design.md`

## Global Constraints

- Existing Gmail Read remains `format=metadata`; `/api/v1/adapters/gmail/observe` must not start fetching bodies.
- V1 accepts exactly one `message_id`; no thread classification, mailbox enumeration, background sync, neighboring-message read or attachment fetch.
- Selected message must be inbound relative to configured owned addresses; outbound/self-authored -> `INVALID_SELECTION` + `message_not_inbound` + zero candidate.
- Gmail FULL content is transient. Raw body, HTML, subject, quoted history, signatures and literal evidence spans never persist to `OperatorObservation`, receipts, `RelationshipEvent`, SQLite, artifacts or structured logs.
- Maximum normalized current-message text accepted for classification is 256 KiB UTF-8. Oversize content -> `content_too_large`; never truncate and classify.
- Attachments, PDFs, images, `.ics` parts and external links are not classified.
- Classifier V1 is deterministic/local ES+EN: `classifier_version="deterministic-process-email-v1"`, `ruleset_version="es-en-2026-09-v1"`.
- `ProcessSignalKind` is exactly `APPLICATION_ACKNOWLEDGED`, `INTERVIEW_PROPOSED`, `STAGE_ADVANCED`, `PROCESS_UPDATED`, `OFFER_RECEIVED`, `REJECTED`.
- Classification disposition is separate: `CLASSIFIED`, `NOT_PROCESS`, `AMBIGUOUS`.
- Confidence is exactly `HIGH | MEDIUM | LOW`; LOW-only evidence never produces an `OperatorObservation`.
- `APPLICATION_ACKNOWLEDGED` never opens a process.
- `INTERVIEW_PROPOSED`, `STAGE_ADVANCED`, `OFFER_RECEIVED`: no open process -> `PROCESS_OPENED`; open process -> `PROCESS_UPDATED`.
- Generic `PROCESS_UPDATED`: no open process -> zero mutation + `no_open_process_to_update`; open process -> `PROCESS_UPDATED`.
- `REJECTED`: no open process -> zero mutation + `no_open_process_to_close`; open process -> `PROCESS_CLOSED`.
- Never fabricate a retroactive `PROCESS_OPENED -> PROCESS_CLOSED` pair to fit a rejection.
- `REJECTED` + any of `INTERVIEW_PROPOSED`, `STAGE_ADVANCED`, `PROCESS_UPDATED`, `OFFER_RECEIVED` -> `AMBIGUOUS` + `conflicting_process_signals` + zero mutation.
- Multiple compatible signals may remain visible, but one request produces at most one candidate `OperatorObservation`.
- Non-mutating classifications are response-only; V1 introduces no classification ledger/database.
- Persisted classifier provenance is typed, bounded and machine-generated only; no provider/user text.
- Existing Operator Bridge preview/import and stale-preview protection remain authoritative; process-email never writes Relationship Memory directly.
- `OPPORTUNITY_PROCESS_EMAIL_ENABLED=false` is independent from `OPPORTUNITY_GMAIL_READ_ENABLED=false`.
- No process-email CLI, auto-send, auto-follow-up or external model backend in V1.

---

## File Map

### New production files

- `app/adapters/gmail_read/direction.py` — shared owned-address + inbound/outbound semantics.
- `app/adapters/gmail_content/__init__.py` — package marker.
- `app/adapters/gmail_content/models.py` — transient content envelope/error contract.
- `app/adapters/gmail_content/normalizer.py` — Gmail FULL MIME parse, body selection, quote/signature isolation, 256 KiB guard.
- `app/adapters/gmail_content/provider.py` — explicit single-message FULL REST read only.
- `app/process_email/__init__.py` — package marker.
- `app/process_email/models.py` — strict selection/signal/classification/projection/preview models.
- `app/process_email/classifier.py` — stable `ProcessClassifier` protocol.
- `app/process_email/deterministic.py` — deterministic bilingual rules.
- `app/process_email/projector.py` — classification + RelationshipAccount -> zero/one candidate observation.
- `app/process_email/service.py` — orchestration without import.
- `app/process_email/api.py` — `POST /api/v1/process-email/preview` only.

### Existing production files modified

- `app/adapters/gmail_read/service.py` — consume shared direction helpers; behavior unchanged.
- `app/operator_bridge/models.py` — optional typed semantic provenance.
- `app/operator_bridge/normalizer.py` — allowlisted provenance keys only.
- `app/main.py` — independent feature flag and injected service route wiring.
- `.env.example` — `OPPORTUNITY_PROCESS_EMAIL_ENABLED=false`.
- `README.md`, `ROADMAP.md` — public contract after verified implementation.

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

- `tests/test_gmail_read_service.py`
- `tests/test_operator_models.py`
- `tests/test_operator_normalizer.py`
- `tests/test_operator_service.py`

Do not modify Radar scoring, Search Health semantics, CV authority, Outreach send gates, application preparation, target scoring or RelationshipService transition rules.

---

### Task 1: Extract Shared Gmail Direction Semantics

**Files:**
- Create: `app/adapters/gmail_read/direction.py`
- Create: `tests/test_gmail_read_direction.py`
- Modify: `app/adapters/gmail_read/service.py`
- Modify: `tests/test_gmail_read_service.py`

**Interfaces:**
- Produces: `normalize_owned_addresses(Iterable[str]) -> frozenset[str]`, `is_outbound(GmailMessageEnvelope, frozenset[str]) -> bool`, `is_inbound(...) -> bool`.
- Later tasks use `is_inbound`; existing Gmail Read uses both direction predicates.

- [ ] **Step 1: Write RED direction tests**

```python
from datetime import datetime, timezone
import pytest

from app.adapters.gmail_read.direction import is_inbound, is_outbound, normalize_owned_addresses
from app.adapters.gmail_read.models import GmailMessageEnvelope

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def msg(sender: str, to: tuple[str, ...], labels: tuple[str, ...]) -> GmailMessageEnvelope:
    return GmailMessageEnvelope(
        message_id="m1", thread_id="t1", internal_date=NOW,
        label_ids=labels, from_address=sender, to_addresses=to,
    )


def test_normalizes_owned_addresses():
    assert normalize_owned_addresses({" OWNER@Example.Test "}) == frozenset({"owner@example.test"})


def test_requires_owned_address():
    with pytest.raises(ValueError, match="owned_addresses"):
        normalize_owned_addresses(set())


def test_inbound_requires_external_sender_and_owned_recipient():
    owned = frozenset({"owner@example.test"})
    assert is_inbound(msg("recruiter@example.test", ("owner@example.test",), ("INBOX",)), owned)
    assert not is_inbound(msg("owner@example.test", ("owner@example.test",), ("INBOX",)), owned)


def test_outbound_requires_sent_owned_sender_and_external_recipient():
    owned = frozenset({"owner@example.test"})
    assert is_outbound(msg("owner@example.test", ("recruiter@example.test",), ("SENT",)), owned)
    assert not is_outbound(msg("owner@example.test", ("owner@example.test",), ("SENT",)), owned)
```

- [ ] **Step 2: Prove RED**

Run: `pytest -q tests/test_gmail_read_direction.py`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement helper**

```python
from collections.abc import Iterable
from app.adapters.gmail_read.models import GmailMessageEnvelope


def normalize_owned_addresses(addresses: Iterable[str]) -> frozenset[str]:
    normalized = frozenset(v.strip().lower() for v in addresses if v.strip())
    if not normalized:
        raise ValueError("owned_addresses must contain at least one address")
    return normalized


def _owned(address: str, owned: frozenset[str]) -> bool:
    return address.strip().lower() in owned


def _recipients(message: GmailMessageEnvelope) -> tuple[str, ...]:
    return (*message.to_addresses, *message.cc_addresses)


def is_outbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool:
    return (
        "SENT" in message.label_ids
        and _owned(message.from_address, owned)
        and any(not _owned(a, owned) for a in _recipients(message))
    )


def is_inbound(message: GmailMessageEnvelope, owned: frozenset[str]) -> bool:
    return (
        not _owned(message.from_address, owned)
        and any(_owned(a, owned) for a in _recipients(message))
    )
```

Refactor `GmailReadService` to use these functions and remove only duplicated private direction code.

- [ ] **Step 4: Focused GREEN**

```bash
pytest -q tests/test_gmail_read_direction.py tests/test_gmail_read_service.py tests/test_gmail_read_normalizer.py tests/test_gmail_read_provider.py tests/test_api_gmail_read.py
```

Expected: PASS, including existing metadata-read behavior.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/gmail_read/direction.py app/adapters/gmail_read/service.py tests/test_gmail_read_direction.py tests/test_gmail_read_service.py
git commit -m "refactor: share gmail direction semantics"
```

---

### Task 2: Add Explicit Gmail FULL Content Transport and MIME Parser

**Files:**
- Create: `app/adapters/gmail_content/__init__.py`
- Create: `app/adapters/gmail_content/models.py`
- Create: `app/adapters/gmail_content/normalizer.py`
- Create: `app/adapters/gmail_content/provider.py`
- Create: `tests/test_gmail_content_normalizer.py`
- Create: `tests/test_gmail_content_provider.py`

**Interfaces:**
- Produces: `GmailContentEnvelope`, `GmailContentError`, `GmailContentProvider.get_message_content(message_id)`, `GmailRestContentProvider`.
- `GmailContentEnvelope` contains existing `GmailMessageEnvelope` metadata + only normalized transient current-message text; no raw payload field.

- [ ] **Step 1: Write RED parser corpus**

Fixture helper:

```python
import base64

def b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
```

Required tests:

1. recursive multipart chooses usable `text/plain` over HTML;
2. HTML-only fallback returns visible text and drops script/style content;
3. filename or `Content-Disposition: attachment` excludes part;
4. `On ... wrote:`, `El ... escribió:`, `-----Original Message-----` remove quoted history;
5. standalone `-- ` removes following signature;
6. invalid base64url -> `gmail_payload_invalid`;
7. supported `text/plain`/`text/html` part present but missing/empty data -> `missing_usable_body`;
8. payload with no supported text MIME candidate at all -> `unsupported_mime`;
9. only quoted history after extraction -> `quoted_content_ambiguous`;
10. normalized current text > `256 * 1024` UTF-8 bytes -> `content_too_large` without truncation.

Happy-path Gmail payload must include real metadata headers so existing `normalize_message_payload()` is exercised.

- [ ] **Step 2: Prove parser RED**

Run: `pytest -q tests/test_gmail_content_normalizer.py`

Expected: FAIL because package does not exist.

- [ ] **Step 3: Implement transient contracts**

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

No body HTML, snippet, raw MIME, provider payload, filename list or attachment bytes in the model.

- [ ] **Step 4: Implement parser with stdlib only**

`normalize_full_message_payload(payload)`:

1. calls existing `normalize_message_payload(payload)` for metadata;
2. recursively traverses root payload + nested `parts`;
3. inspects each part's `mimeType`, `filename`, body data and `Content-Disposition` header;
4. records whether any supported text MIME part existed;
5. decodes base64url with repaired padding and strict UTF-8;
6. prefers first usable plain candidate; else first usable HTML candidate;
7. if no supported text MIME part existed -> `unsupported_mime`;
8. if supported parts existed but no usable text -> `missing_usable_body`;
9. strips known quoted blocks/signature;
10. checks 256 KiB bound after current-message normalization.

Decode:

```python
padding = "=" * (-len(data) % 4)
raw = base64.urlsafe_b64decode(data + padding)
text = raw.decode("utf-8", errors="strict")
```

HTML fallback uses a small `HTMLParser` subclass; skip data inside `script`/`style`, insert line boundaries for `p`, `div`, `br`, `li`, `tr`. No new dependency.

Known quote markers:

```python
_QUOTE_MARKERS = (
    re.compile(r"(?im)^On .+ wrote:\s*$"),
    re.compile(r"(?im)^El .+ escribió:\s*$"),
    re.compile(r"(?im)^-----Original Message-----\s*$"),
)
```

Take text before earliest marker; cut at standalone `-- ` signature delimiter. If current part becomes empty -> `quoted_content_ambiguous`.

- [ ] **Step 5: Parser GREEN**

Run: `pytest -q tests/test_gmail_content_normalizer.py`

Expected: PASS.

- [ ] **Step 6: Write RED provider tests**

Prove exactly one GET to `/gmail/v1/users/me/messages/m1`, `format=full`, bearer token in request only, and no thread/list/search method. Test 401/403/404/429/timeout/invalid JSON; exception text contains bounded error code only, never access token or provider response body.

- [ ] **Step 7: Implement single-message provider**

```python
class GmailContentProvider(Protocol):
    async def get_message_content(self, message_id: str) -> GmailContentEnvelope: ...
```

`GmailRestContentProvider` requests only `messages/{quote(message_id)}` with `params={"format":"full"}` and passes JSON to `normalize_full_message_payload`. Map HTTP failures to the existing Gmail codes (`gmail_unauthorized`, `gmail_forbidden`, `gmail_not_found`, `gmail_rate_limited`, `gmail_provider_error`, `gmail_timeout`).

- [ ] **Step 8: GREEN + commit**

```bash
pytest -q tests/test_gmail_content_normalizer.py tests/test_gmail_content_provider.py tests/test_gmail_read_provider.py
python -m compileall -q app/adapters/gmail_content

git add app/adapters/gmail_content tests/test_gmail_content_normalizer.py tests/test_gmail_content_provider.py
git commit -m "feat: add explicit gmail content reader"
```

---

### Task 3: Define Process Email Models and Classifier Interface

**Files:**
- Create: `app/process_email/__init__.py`
- Create: `app/process_email/models.py`
- Create: `app/process_email/classifier.py`
- Create: `tests/test_process_email_models.py`

**Interfaces:**
- Produces exact signal/confidence/disposition/status literals, transient evidence models, selection, classification, projection, preview and `ProcessClassifier` protocol.

- [ ] **Step 1: Write RED strict-model tests**

Exact literals:

```python
ProcessSignalKind = Literal[
    "APPLICATION_ACKNOWLEDGED", "INTERVIEW_PROPOSED", "STAGE_ADVANCED",
    "PROCESS_UPDATED", "OFFER_RECEIVED", "REJECTED",
]
ProcessConfidence = Literal["HIGH", "MEDIUM", "LOW"]
ClassificationDisposition = Literal["CLASSIFIED", "NOT_PROCESS", "AMBIGUOUS"]
ProcessEmailStatus = Literal[
    "CLASSIFIED", "NOT_PROCESS", "AMBIGUOUS", "CONTENT_UNAVAILABLE",
    "PROVIDER_ERROR", "INVALID_SELECTION", "BLOCKED",
]
```

Test strict extra rejection, timezone-aware `observed_at`, bounded `reason_code`, valid evidence offsets, and `external_actions=[]` invariant.

Disposition shape tests are explicit:

```text
CLASSIFIED -> signals must be non-empty
NOT_PROCESS -> signals must be empty
AMBIGUOUS -> signals may be empty OR contain conflicting positive evidence for transient review
```

If `AMBIGUOUS` contains positive signals, `warnings` must contain `conflicting_process_signals`; no candidate observation may be attached to the final preview.

- [ ] **Step 2: Prove RED**

Run: `pytest -q tests/test_process_email_models.py`

Expected: FAIL because package does not exist.

- [ ] **Step 3: Implement models**

```python
class EvidenceSpan(StrictProcessEmailModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_range(self):
        if self.end <= self.start:
            raise ValueError("evidence span end must be after start")
        return self

class ProcessSignal(StrictProcessEmailModel):
    kind: ProcessSignalKind
    confidence: ProcessConfidence
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    evidence_spans: list[EvidenceSpan] = Field(min_length=1)

class ProcessClassification(StrictProcessEmailModel):
    disposition: ClassificationDisposition
    classifier_version: Literal["deterministic-process-email-v1"]
    ruleset_version: Literal["es-en-2026-09-v1"]
    signals: list[ProcessSignal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

Validator:
- CLASSIFIED + empty signals -> reject;
- NOT_PROCESS + non-empty signals -> reject;
- AMBIGUOUS + non-empty signals requires `conflicting_process_signals` warning.

`ProcessEmailSelection` exactly: `account_id`, optional `contact_id`, `message_id`, `selected_by`.

`ProcessEmailPreview` exactly: `status`, `classifier_version`, `ruleset_version`, `source_ref`, `observed_at`, `signals`, `warnings`, optional `proposed_observation`, optional `operator_preview`, `external_actions`. If `proposed_observation is None`, `operator_preview` must also be None. If status is `AMBIGUOUS`, proposed observation must be None.

- [ ] **Step 4: Add stable protocol**

```python
class ProcessClassifier(Protocol):
    def classify(self, text: str) -> ProcessClassification: ...
```

No provider/DB/network dependency.

- [ ] **Step 5: GREEN + commit**

```bash
pytest -q tests/test_process_email_models.py
python -m compileall -q app/process_email

git add app/process_email/__init__.py app/process_email/models.py app/process_email/classifier.py tests/test_process_email_models.py
git commit -m "feat: add process email classification contracts"
```

---

### Task 4: Implement Deterministic ES/EN Classification

**Files:**
- Create: `app/process_email/deterministic.py`
- Create: `tests/test_process_email_classifier.py`

**Interfaces:**
- Input: normalized current-message `str` only.
- Output: deterministic `ProcessClassification`; no clock, network, filesystem, DB or model API.

- [ ] **Step 1: Write RED bilingual semantic corpus**

Required HIGH examples:

```text
ACK: "We received your application." / "Hemos recibido tu candidatura."
INTERVIEW: "We would like to invite you to an interview." / "Queremos invitarte a una entrevista."
STAGE: "You have advanced to the next stage of our hiring process." / "Avanzaste a la siguiente etapa del proceso."
UPDATE: "We need to reschedule your interview to Thursday." / "Necesitamos reprogramar tu entrevista para el jueves."
OFFER: "We are pleased to offer you the position." / "Nos complace ofrecerte el puesto."
REJECTED: "We will not be moving forward with your application." / "No continuaremos con tu candidatura."
```

Required guards:

```text
"Our interview process normally takes two weeks." -> no INTERVIEW_PROPOSED
"If selected, you may be invited to interview." -> no INTERVIEW_PROPOSED
"We are not yet scheduling interviews." -> no INTERVIEW_PROPOSED
"The compensation range for this role is USD 80k-100k." -> no OFFER_RECEIVED
"We are still reviewing applications." -> no REJECTED
"Aún no tomamos una decisión." -> no REJECTED
```

LOW-only examples:

```text
"We will share next steps soon."
"Tenemos novedades sobre tu perfil."
```

They may emit `PROCESS_UPDATED` LOW with warning `low_confidence_only`; projector must later produce zero mutation.

Explicit NOT_PROCESS:

```text
"Automatic reply: I am out of the office until Monday."
"Respuesta automática: estoy fuera de la oficina hasta el lunes."
```

Unknown generic `"Hello, thanks for your message."` -> AMBIGUOUS, not NOT_PROCESS.

- [ ] **Step 2: Prove RED**

Run: `pytest -q tests/test_process_email_classifier.py`

Expected: FAIL because deterministic classifier does not exist.

- [ ] **Step 3: Implement versioned rule tables**

Constants:

```python
CLASSIFIER_VERSION = "deterministic-process-email-v1"
RULESET_VERSION = "es-en-2026-09-v1"
```

Reason codes exactly:

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

Every positive regex match yields `EvidenceSpan(match.start(), match.end(), match.group(0))`. Rules must be phrase/composition-based, never bare `"interview" in text`.

Minimum guard patterns:

```python
_HYPOTHETICAL = (
    re.compile(r"\bif selected\b", re.I),
    re.compile(r"\bmay be invited\b", re.I),
    re.compile(r"\bsi (?:sos|eres|resultas) seleccionad[oa]\b", re.I),
    re.compile(r"\bpodr[ií]as? ser invitad[oa]\b", re.I),
)
_NEGATED_INTERVIEW = (
    re.compile(r"\bnot yet scheduling interviews\b", re.I),
    re.compile(r"\ba[uú]n no (?:estamos )?coordinando entrevistas\b", re.I),
)
_GENERIC_DESCRIPTION = (
    re.compile(r"\bour interview process normally\b", re.I),
    re.compile(r"\bnuestro proceso de entrevistas normalmente\b", re.I),
)
```

- [ ] **Step 4: Implement multi-signal/conflict semantics**

Compatible mutation-driving priority:

```text
OFFER_RECEIVED > STAGE_ADVANCED > INTERVIEW_PROPOSED > PROCESS_UPDATED > APPLICATION_ACKNOWLEDGED
```

Retain all compatible matched signals in deterministic order. `REJECTED + APPLICATION_ACKNOWLEDGED` is compatible and REJECTED drives projection. `REJECTED + INTERVIEW/STAGE/UPDATE/OFFER` returns `ProcessClassification(disposition="AMBIGUOUS", signals=<conflicting transient signals>, warnings=["conflicting_process_signals"], ...)`.

No positive match: explicit out-of-office -> NOT_PROCESS with empty signals; otherwise AMBIGUOUS with empty signals.

- [ ] **Step 5: GREEN + determinism test**

```bash
pytest -q tests/test_process_email_classifier.py
```

Add repeated-call equality/byte-equal JSON regression. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/process_email/deterministic.py tests/test_process_email_classifier.py
git commit -m "feat: classify hiring process email signals"
```

---

### Task 5: Typed Semantic Provenance and Relationship-Aware Projection

**Files:**
- Modify: `app/operator_bridge/models.py`
- Modify: `app/operator_bridge/normalizer.py`
- Modify: `tests/test_operator_models.py`
- Modify: `tests/test_operator_normalizer.py`
- Create: `app/process_email/projector.py`
- Create: `tests/test_process_email_projector.py`

**Interfaces:**
- Produces `ObservationSemanticProvenance` and `ProcessEventProjector.project(...) -> ProcessProjection`.
- Existing observations with no semantic provenance remain unchanged.

- [ ] **Step 1: RED provenance strictness**

```python
provenance = ObservationSemanticProvenance(
    producer="PROCESS_EMAIL_CLASSIFIER",
    producer_version="deterministic-process-email-v1",
    policy_version="es-en-2026-09-v1",
    classification="INTERVIEW_PROPOSED",
    reason_code="INTERVIEW_INVITATION_EXPLICIT",
)
```

Prove arbitrary `evidence_text`, `body`, `subject`, dict metadata are rejected by strict models; existing observations still validate without provenance.

- [ ] **Step 2: Implement bounded provenance**

```python
class ObservationSemanticProvenance(StrictOperatorModel):
    producer: Literal["PROCESS_EMAIL_CLASSIFIER"]
    producer_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    policy_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    classification: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    reason_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
```

Add `semantic_provenance: ObservationSemanticProvenance | None = None` to `OperatorObservation`.

- [ ] **Step 3: RED/implement normalizer allowlist**

Expected additional event metadata keys only:

```text
semantic_producer
semantic_producer_version
semantic_policy_version
semantic_classification
semantic_reason_code
```

Implementation:

```python
if observation.semantic_provenance is not None:
    p = observation.semantic_provenance
    metadata.update({
        "semantic_producer": p.producer,
        "semantic_producer_version": p.producer_version,
        "semantic_policy_version": p.policy_version,
        "semantic_classification": p.classification,
        "semantic_reason_code": p.reason_code,
    })
```

Do not change event identity logic. Observation hash includes typed provenance automatically.

- [ ] **Step 4: Operator GREEN**

```bash
pytest -q tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_operator_service.py tests/test_api_operator_bridge.py
```

Expected: PASS.

- [ ] **Step 5: Write RED projector matrix**

Test:

```text
ACK + closed/open -> none
INTERVIEW + closed -> PROCESS_OPENED
INTERVIEW + open -> PROCESS_UPDATED
STAGE + closed -> PROCESS_OPENED
STAGE + open -> PROCESS_UPDATED
UPDATE + closed -> none + no_open_process_to_update
UPDATE + open -> PROCESS_UPDATED
OFFER + closed -> PROCESS_OPENED
OFFER + open -> PROCESS_UPDATED
REJECTED + closed -> none + no_open_process_to_close
REJECTED + open -> PROCESS_CLOSED
LOW-only -> none + low_confidence_only
AMBIGUOUS -> none
```

Observation ID for driving signal exactly `gmail-message:m1:process-signal:INTERVIEW_PROPOSED`.

- [ ] **Step 6: Implement projector**

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

Only HIGH/MEDIUM can drive mutation. If mutation needs relationship state and account is `None`, return zero candidate + `unknown_relationship_account`.

Normalized reasons:

```python
_REASON = {
    "INTERVIEW_PROPOSED": "explicit interview invitation observed",
    "STAGE_ADVANCED": "explicit hiring-stage advancement observed",
    "PROCESS_UPDATED": "explicit hiring-process update observed",
    "OFFER_RECEIVED": "explicit employment offer observed",
    "REJECTED": "explicit process rejection observed",
}
```

Candidate fields: source type EMAIL_PROVIDER, source name gmail, source ref `gmail:message:<id>`, no process label, typed semantic provenance from driving signal/rule.

- [ ] **Step 7: GREEN + commit**

```bash
pytest -q tests/test_process_email_projector.py tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_operator_service.py

git add app/operator_bridge/models.py app/operator_bridge/normalizer.py app/process_email/projector.py tests/test_operator_models.py tests/test_operator_normalizer.py tests/test_process_email_projector.py
git commit -m "feat: project classified process facts safely"
```

---

### Task 6: Orchestrate Read -> Classify -> Existing Operator Preview

**Files:**
- Create: `app/process_email/service.py`
- Create: `tests/test_process_email_service.py`

**Interfaces:**
- Consumes `GmailContentProvider`, owned addresses, `ProcessClassifier`, `ProcessEventProjector`, optional relationship repository and Operator Bridge.
- Produces `ProcessEmailService.preview(ProcessEmailSelection) -> ProcessEmailPreview`.
- Has no import/write method.

- [ ] **Step 1: Write RED service tests**

Test exact one-message request, inbound interview candidate+operator preview, outbound invalid selection with zero classifier call, ACK-only non-mutating response, LOW/conflict/rejection-no-open/update-no-open zero candidate, provider failures, content failures, missing operator bridge when mutation exists, and no relationship event before confirmation.

Error mapping:

```text
gmail_unauthorized/gmail_forbidden/gmail_not_found/gmail_rate_limited/gmail_provider_error/gmail_timeout -> PROVIDER_ERROR
unsupported_mime/missing_usable_body/content_too_large/quoted_content_ambiguous/gmail_payload_invalid -> CONTENT_UNAVAILABLE
message_not_inbound -> INVALID_SELECTION
unknown_relationship_account/operator_bridge_unavailable -> BLOCKED
```

- [ ] **Step 2: Prove RED**

Run: `pytest -q tests/test_process_email_service.py`

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement constructor**

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

- [ ] **Step 4: Implement fail-closed orchestration order**

```text
fetch selected content
-> validate inbound
-> classify current_message_text
-> if NOT_PROCESS/AMBIGUOUS return transient preview, zero candidate
-> read account if projection is needed
-> projector derives zero/one candidate
-> if zero candidate return classification + bounded warnings
-> require Operator Bridge
-> bridge.preview(candidate)
-> return candidate + existing ObservationPreview
```

Never call `import_observation` here.

`source_ref` is `gmail:message:<id>`; `observed_at` is provider internal date. Evidence spans remain in response only.

- [ ] **Step 5: Logging privacy regression**

Using `caplog`, place sentinel strings in subject/body/evidence and assert they never appear in logs. Module may log static error code/provider name only, not full request/response or content.

- [ ] **Step 6: GREEN + commit**

```bash
pytest -q tests/test_process_email_service.py tests/test_process_email_projector.py tests/test_process_email_classifier.py

git add app/process_email/service.py tests/test_process_email_service.py
git commit -m "feat: preview classified process emails"
```

---

### Task 7: API + Independent Feature Flag

**Files:**
- Create: `app/process_email/api.py`
- Create: `tests/test_api_process_email.py`
- Modify: `app/main.py`
- Modify: `.env.example`

**Interfaces:**
- One route only: `POST /api/v1/process-email/preview`.
- `create_app` gains injected `process_email_service` + `enable_process_email`; no token/OAuth/provider construction.

- [ ] **Step 1: RED API boundary tests**

Prove route absent by default. Enabled + no service -> 503 `{"detail":"process_email_unavailable"}`. Injected fake service receives exact `ProcessEmailSelection`. Response `external_actions=[]`. OpenAPI has no `/api/v1/process-email/import`.

- [ ] **Step 2: Implement router**

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

- [ ] **Step 3: Add flag/wiring**

`_process_email_enabled()` parses only `OPPORTUNITY_PROCESS_EMAIL_ENABLED`, default false, using same accepted boolean spellings as existing feature flags.

`create_app` adds:

```python
process_email_service: ProcessEmailService | None = None,
enable_process_email: bool | None = None,
```

and includes router only when enabled. No default Gmail content client/token/relationship DB creation.

Append `.env.example`:

```text
OPPORTUNITY_PROCESS_EMAIL_ENABLED=false
```

- [ ] **Step 4: GREEN + regression + commit**

```bash
pytest -q tests/test_api_process_email.py tests/test_api_gmail_read.py tests/test_api_operator_bridge.py
python -m compileall -q app/main.py app/process_email

git add app/process_email/api.py app/main.py .env.example tests/test_api_process_email.py
git commit -m "feat: expose process email preview route"
```

---

### Task 8: End-to-End Privacy, Confirmation and Stale-Preview Harness

**Files:**
- Create: `tests/test_process_email_privacy.py`
- Modify only narrow Task 2-7 production files if a new RED regression proves a bug.

**Interfaces:**
- Proves FULL fixture -> transient classifier -> candidate -> existing preview -> explicit existing import -> RelationshipEvent.

- [ ] **Step 1: RED end-to-end interview test**

Create temp Relationship SQLite, register `example-co`, use real Operator Bridge and fake content provider. Subject sentinel `PRIVATE SUBJECT SENTINEL`; body includes explicit interview + `PRIVATE BODY SENTINEL`.

Before import:

```python
assert repo.list_events("example-co") == []
assert preview.proposed_observation is not None
assert preview.operator_preview.status == "IMPORTABLE"
```

Then call existing `bridge.import_observation(...)` using candidate + returned preview hash + explicit confirmer/time. Assert one PROCESS_OPENED event.

- [ ] **Step 2: Persistence allowlist assertion**

Inspect repository models and raw SQLite `payload_json`; assert none contains subject/body/evidence sentinels or literal interview sentence. Event metadata must carry machine provenance values only:

```text
semantic_producer=PROCESS_EMAIL_CLASSIFIER
semantic_producer_version=deterministic-process-email-v1
semantic_policy_version=es-en-2026-09-v1
semantic_classification=INTERVIEW_PROPOSED
semantic_reason_code=INTERVIEW_INVITATION_EXPLICIT
```

- [ ] **Step 3: Required semantic E2E regressions**

Zero persisted event unless explicitly noted:

```text
ATS receipt -> no PROCESS_OPENED
outbound operator email -> INVALID_SELECTION
rejection without open process -> no fabricated event
current rejection + quoted old interview, with open process -> PROCESS_CLOSED only
compensation range -> no OFFER
hypothetical interview -> no candidate
LOW-only -> no candidate
conflicting reject + interview -> AMBIGUOUS, no candidate
```

- [ ] **Step 4: Stale-preview test**

Generate interview preview, mutate relationship state through a different valid event, then import old candidate/hash. Expected `BLOCKED_STALE_PREVIEW`; no process-email event appended.

- [ ] **Step 5: Idempotency test**

Import accepted process-email observation twice. Expected first `IMPORTED`, second `ALREADY_IMPORTED`, one event for identity.

- [ ] **Step 6: GREEN + commit**

```bash
pytest -q tests/test_process_email_privacy.py tests/test_process_email_service.py tests/test_operator_service.py

git add tests/test_process_email_privacy.py app/adapters/gmail_content app/process_email app/operator_bridge
git commit -m "test: prove process email privacy boundaries"
```

Only stage production files if a RED regression required a minimal fix.

---

### Task 9: Product Documentation and Release Contract

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Create: `tests/test_process_email_release_contract.py`

- [ ] **Step 1: RED docs contract**

Require public docs to contain:

```text
Process Email
selected inbound message
body access != body persistence
classification != authority
APPLICATION_ACKNOWLEDGED
OPPORTUNITY_PROCESS_EMAIL_ENABLED=false
human confirmation
```

And not claim mailbox-wide sync, automatic process mutation/follow-up or external LLM classification.

- [ ] **Step 2: Update README**

Document:

```text
explicit inbound Gmail message
-> transient FULL content
-> deterministic ES/EN signals + evidence preview
-> zero/one candidate OperatorObservation
-> existing Operator Bridge preview
-> explicit human confirm/import
```

State body/subject/evidence transient; no attachments/threads/mailbox scan; ACK != process open.

- [ ] **Step 3: Update ROADMAP**

Mark classifier implemented only after Tasks 1-8 pass. Keep WhatsApp/conversation-provider separate/future. Do not claim Search Health offer metrics.

- [ ] **Step 4: GREEN + commit**

```bash
pytest -q tests/test_process_email_release_contract.py

git add README.md ROADMAP.md tests/test_process_email_release_contract.py
git commit -m "docs: document process email classifier"
```

---

### Task 10: Full Verification, Review, PR and Merge Gate

**Files:** no new behavior unless verification proves a bug; each behavioral fix starts with a narrow RED regression.

- [ ] **Step 1: Full local verification**

```bash
python -m pytest -q
python -m compileall -q app tests
git diff --check main...HEAD
```

Expected: zero failures; final count > baseline 619 tests; compile/diff clean.

- [ ] **Step 2: Scope/privacy checks**

```bash
git diff --name-only main...HEAD
git ls-files -- '*.local.*' 'state/*.sqlite3*' 'artifacts/**'
```

No newly tracked private evidence. Inspect production diff for raw-content fields and unrelated subsystem changes.

- [ ] **Step 3: Explicit metadata-read regression**

```bash
pytest -q \
  tests/test_gmail_read_provider.py::test_get_message_uses_metadata_read_endpoint_and_bearer_token \
  tests/test_gmail_read_provider.py::test_get_thread_uses_metadata_read_endpoint
```

Expected: PASS; existing adapter still requests `format=metadata`.

- [ ] **Step 4: Spec checklist review**

Verify every item:

```text
one message only
inbound only
FULL only in gmail_content
256 KiB fail closed
unsupported MIME distinct from missing supported body
attachments excluded
ES/EN deterministic
LOW/ambiguous/conflict zero mutation
ACK != process open
rejection without open != fabricated close
typed provenance only
zero direct relationship writes
no process-email import route
independent default-false feature flag
no new dependency
no external LLM
no sensitive persistence/logging
```

- [ ] **Step 5: Open implementation PR**

Title:

```text
feat: add evidence-aware process email classifier
```

PR body includes privacy/content-read boundary, versions, transition rules, human-confirmation boundary, no mailbox sync, no LLM/new dependency, exact test/compile/diff evidence and review regressions.

- [ ] **Step 6: Require exact-head CI**

Existing workflow must succeed on exact PR head: pytest, compile, diff/private-file guard, recruiter previews, SHA-bound offline runtime build + Python 3.12/3.13 offline verification. Do not weaken existing jobs.

- [ ] **Step 7: Resolve findings with TDD**

```text
RED regression -> minimal fix -> focused GREEN -> full suite -> diff review -> commit
```

No merge with unresolved privacy/lifecycle/stale-preview finding.

- [ ] **Step 8: Merge only verified head and post-merge verify**

After merge, verify `merged=true`, merge commit on `main`, and successful post-merge workflow on that commit before declaring V1 complete.

---

## Plan Self-Review

- **Spec coverage:** inbound selection, separate FULL transport, MIME/base64/HTML, quote/signature handling, 256 KiB bound, `unsupported_mime` vs `missing_usable_body`, signal/disposition taxonomy, confidence, bilingual deterministic rules, multi-signal conflict, relationship-state projection, response-only non-mutating evidence, typed provenance, API/flag, existing confirmation boundary, privacy regression, docs and CI all map to tasks.
- **Placeholder scan:** no TBD/TODO or undefined implementation action remains; code tasks include concrete signatures, literals, errors and test commands.
- **Type consistency:** Task 2 defines `GmailContentEnvelope`; Task 3 defines classification types/protocol; Task 4 implements that protocol; Task 5 defines provenance/projector; Task 6 consumes those exact types; Task 7 exposes the same selection/preview types.
- **Ambiguity fix:** `NOT_PROCESS` always has empty signals; `AMBIGUOUS` may retain conflicting positive signals for transient review but can never carry a candidate observation. This matches the evidence-visible/fail-closed contract.
- **MIME fix:** `unsupported_mime` means there was no supported text MIME candidate; `missing_usable_body` means supported text MIME existed but yielded no usable content.
- **Dependency direction:** provider transports; classifier interprets; projector maps to domain; service orchestrates without import; Operator Bridge remains sole write boundary.
- **YAGNI:** no threads, mailbox sync, workers, attachments, link crawling, salary/role extraction, sentiment, prediction, classification ledger, Search Health schema change, CLI or LLM backend.
- **Privacy:** source text lives only in transient content/evidence response. Persisted provenance is bounded identifiers only.
- **TDD:** each behavioral task begins RED, proves failure, implements minimum, runs GREEN, then commits.
