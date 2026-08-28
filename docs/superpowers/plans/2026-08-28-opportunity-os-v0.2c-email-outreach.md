# Opportunity OS V0.2C Email-first + Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic V0.2C outreach core that turns a validated V0.2B `ApplicationPacket` into a verified contact resolution, evidence-bounded `OutreachBrief`, exact Gmail draft snapshot, explicit approval, separate explicit send request, idempotent send authorization, and durable receipt/ledger state without embedding Gmail or Apollo calls in the core.

**Architecture:** Keep V0.2C isolated in a new `app/outreach/` package. Radar gains only one first-class typed output: vacancy-published application email hints with provenance. The outreach core consumes `RadarAssessment` + `ApplicationPacket`, persists local private state in SQLite, and exposes pure service boundaries that ChatGPT can operate around using connected Gmail/Apollo tools.

**Tech Stack:** Python 3.12, Pydantic v2, sqlite3, existing SHA-256 canonical hashing pattern, pytest, GitHub Actions. No new runtime network dependency, queue, daemon, LangChain/LangGraph, Gmail SDK, or Apollo SDK.

**Spec:** `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md`

## Global Constraints

- `main` base is `2f3b0676c64eb6f7cb9831c57ff85258d5e2ced0` with V0.2A1 + V0.2B merged.
- Python remains `>=3.12`.
- Deterministic core must never call Gmail or Apollo directly.
- Contact priority is `PUBLISHED_VACANCY_EMAIL > OFFICIAL_HR_EMAIL > VERIFIED_RECRUITER > MANUAL_FORM`.
- Never infer or generate email addresses from names/domains.
- `HIGH` and `MEDIUM` may prepare automatically; `STRETCH` requires explicit manual promotion.
- `ApplicationPacket` is authoritative for CV track, selected facts/evidence, unresolved gaps, CV path/hash, and packet hash.
- ChatGPT copy is bounded by `OutreachBrief + ApplicationPacket`; V0.2C adds no LLM dependency.
- Gmail draft creation remains an explicit external user-requested action.
- Approval is tied to exact semantic draft content; approval is not a send command.
- Sending requires a separate explicit `SendRequest`.
- Apollo paid enrichment remains external and requires connector-level explicit credit confirmation.
- Real state stays private: `state/outreach.local.sqlite3`, real application artifacts, Gmail IDs, real bodies, approvals, send requests, receipts.
- CI remains offline and public fixtures remain fictional.
- Existing V0.1/V0.2A/V0.2B tests must stay green.

## File Structure

Create a focused package:

```text
app/outreach/
  __init__.py           # package marker only
  models.py             # strict V0.2C contracts and policy types
  hashing.py            # canonical semantic hashes for briefs/drafts/manifests/send keys
  repository.py         # SQLite persistence + append-only event ledger
  contact.py            # deterministic contact candidate ranking/resolution
  preparation.py        # ApplicationPacket/RadarAssessment -> OutreachBrief
  draft.py              # DraftSnapshot construction + exact semantic identity
  approval.py           # ApprovalRecord creation/revocation/expiry checks
  send.py               # SendRequest + SendGate + SendReceipt validation
  service.py            # thin orchestration over the pure units; no provider calls
```

Modify only where required:

```text
app/radar/models.py
app/radar/extractor.py
README.md
pyproject.toml
.gitignore
.github/workflows/tests.yml
```

Tests:

```text
tests/test_radar_application_contact.py
tests/test_outreach_models.py
tests/test_outreach_repository.py
tests/test_outreach_contact.py
tests/test_outreach_preparation.py
tests/test_outreach_draft.py
tests/test_outreach_approval.py
tests/test_outreach_send.py
tests/test_outreach_service.py
tests/test_outreach_release_contract.py
```

---

### Task 1: Promote Published Application Email to Typed Radar Data

**Files:**
- Modify: `app/radar/models.py`
- Modify: `app/radar/extractor.py`
- Create: `tests/test_radar_application_contact.py`

**Interfaces:**
- Consumes: existing `Opportunity`, `DerivedValue`, `OpportunityEnrichment`, `_EMAIL_RE`.
- Produces: `ApplicationContactHint`; `OpportunityEnrichment.application_contact_hints`; deterministic vacancy email extraction with source span provenance.

- [ ] **Step 1: Write failing model/extractor tests**

Create `tests/test_radar_application_contact.py` with focused fictional cases:

```python
from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.radar.extractor import RuleBasedRequirementExtractor

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _opportunity(description: str) -> Opportunity:
    return Opportunity(
        id="opp-email-1",
        source="manual",
        source_id="fixture-email-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="GIS Developer",
        description=description,
        discovered_at=NOW,
        published_at=NOW,
    )


def test_published_email_is_extracted_with_provenance() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity("Apply by sending your CV to Careers@Example.Test.")
    )

    assert enrichment.application_mode == "DIRECT_EMAIL"
    assert len(enrichment.application_contact_hints) == 1
    hint = enrichment.application_contact_hints[0]
    assert hint.kind == "PUBLISHED_EMAIL"
    assert hint.value == "careers@example.test"
    assert hint.source_field == "description"
    assert hint.source_text == "Apply by sending your CV to Careers@Example.Test."
    assert hint.extraction_method == "explicit_rule"
    assert hint.confidence == 1.0


def test_no_email_never_generates_conventional_address() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity("Apply through our careers page. Example Labs is hiring.")
    )

    assert enrichment.application_contact_hints == []
    assert enrichment.application_mode != "DIRECT_EMAIL"


def test_duplicate_same_email_is_deduplicated_case_insensitively() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity(
            "Send CV to careers@example.test. Questions: Careers@Example.Test."
        )
    )

    assert [hint.value for hint in enrichment.application_contact_hints] == [
        "careers@example.test"
    ]
```

- [ ] **Step 2: Run the targeted tests and confirm RED**

Run:

```bash
python -m pytest tests/test_radar_application_contact.py -v
```

Expected: import/model failures because `ApplicationContactHint` and `application_contact_hints` do not exist.

- [ ] **Step 3: Add the strict contract to `app/radar/models.py`**

Add:

```python
ApplicationContactHintKind = Literal[
    "PUBLISHED_EMAIL",
    "OFFICIAL_HR_EMAIL",
    "RECRUITER",
    "MANUAL_CHANNEL",
]


class ApplicationContactHint(StrictRadarModel):
    kind: ApplicationContactHintKind
    value: str = Field(min_length=1)
    source_url: str | None = None
    source_field: str = Field(min_length=1)
    source_text: str | None = None
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)
    discovered_at: datetime

    @field_validator("discovered_at")
    @classmethod
    def discovered_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)
```

Add to `OpportunityEnrichment`:

```python
application_contact_hints: list[ApplicationContactHint] = Field(default_factory=list)
```

- [ ] **Step 4: Add deterministic extraction to `app/radar/extractor.py`**

Import `ApplicationContactHint` and implement:

```python
def _extract_published_email_hints(
    opportunity: Opportunity,
) -> list[ApplicationContactHint]:
    by_email: dict[str, ApplicationContactHint] = {}
    for sentence in _sentences(opportunity.description):
        for match in _EMAIL_RE.finditer(sentence):
            email = match.group(0).strip().casefold()
            by_email.setdefault(
                email,
                ApplicationContactHint(
                    kind="PUBLISHED_EMAIL",
                    value=email,
                    source_url=opportunity.source_url,
                    source_field="description",
                    source_text=sentence,
                    extraction_method="explicit_rule",
                    confidence=1.0,
                    discovered_at=opportunity.discovered_at,
                ),
            )
    return list(by_email.values())
```

In `extract()` compute once:

```python
application_contact_hints = _extract_published_email_hints(opportunity)
```

Pass it to `OpportunityEnrichment(...)` and make `_application_mode` consume the hints rather than rescanning free text:

```python
def _application_mode(
    opportunity: Opportunity,
    hints: list[ApplicationContactHint],
) -> str:
    if any(hint.kind == "PUBLISHED_EMAIL" for hint in hints):
        return "DIRECT_EMAIL"
    if opportunity.source.casefold() in _DIRECT_ATS_SOURCES:
        return "HOSTED_MANUAL"
    return "UNKNOWN"
```

- [ ] **Step 5: Run targeted + radar regressions**

Run:

```bash
python -m pytest tests/test_radar_application_contact.py tests/test_radar_extractor.py tests/test_radar_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add app/radar/models.py app/radar/extractor.py tests/test_radar_application_contact.py
git commit -m "feat: type published application emails"
```

---

### Task 2: Add Strict Outreach Contracts and Semantic Hashing

**Files:**
- Create: `app/outreach/__init__.py`
- Create: `app/outreach/models.py`
- Create: `app/outreach/hashing.py`
- Create: `tests/test_outreach_models.py`

**Interfaces:**
- Consumes: `SearchIntent`, radar `ApplicationMode`, existing canonical SHA pattern.
- Produces: all V0.2C immutable contracts used by Tasks 3-8; `canonical_sha256`, `draft_semantic_payload`, `brief_semantic_payload`, `batch_manifest_sha256`, `send_idempotency_key`.

- [ ] **Step 1: Write failing strict-contract/hash tests**

Cover aware timestamps, `extra="forbid"`, required verification for actionable email, semantic hashes excluding provider IDs/timestamps, and attachment filename sensitivity:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.outreach.hashing import batch_manifest_sha256, draft_sha256
from app.outreach.models import ContactResolution, DraftAttachment, DraftSnapshot

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _draft(provider_draft_id: str, created_at=NOW, filename="Alex_Example_CV.pdf"):
    return DraftSnapshot(
        draft_snapshot_id="snap-1",
        opportunity_id="opp-1",
        brief_sha256="a" * 64,
        application_packet_sha256="b" * 64,
        provider="gmail",
        provider_draft_id=provider_draft_id,
        to=["careers@example.test"],
        subject="Application — GIS Developer",
        body_canonical="Hello\n\nAttached is my CV.",
        attachments=[DraftAttachment(filename=filename, sha256="c" * 64, role="CV")],
        cv_sha256="c" * 64,
        content_type="text/plain",
        verification_basis="CREATED_EXACT",
        created_at=created_at,
        verified_at=created_at,
        draft_sha256="0" * 64,
    )


def test_provider_id_and_time_do_not_change_semantic_draft_hash() -> None:
    left = _draft("draft-a")
    right = _draft("draft-b", NOW + timedelta(minutes=5))
    assert draft_sha256(left) == draft_sha256(right)


def test_attachment_filename_changes_semantic_draft_hash() -> None:
    left = _draft("draft-a", filename="Alex_Example_CV.pdf")
    right = _draft("draft-a", filename="wrong-name.pdf")
    assert draft_sha256(left) != draft_sha256(right)


def test_actionable_email_resolution_cannot_be_unverified() -> None:
    with pytest.raises(ValueError, match="actionable email"):
        ContactResolution(
            opportunity_id="opp-1",
            channel="PUBLISHED_VACANCY_EMAIL",
            email="careers@example.test",
            organization="Example Labs",
            source_kind="VACANCY",
            source_ref="https://example.test/jobs/1",
            confidence=1.0,
            verification_status="UNVERIFIED",
            resolution_reason="fixture",
            resolved_at=NOW,
            resolver_version="contact-v1",
        )


def test_batch_manifest_is_order_independent() -> None:
    assert batch_manifest_sha256(["b" * 64, "a" * 64]) == batch_manifest_sha256(
        ["a" * 64, "b" * 64]
    )
```

- [ ] **Step 2: Run and confirm RED**

```bash
python -m pytest tests/test_outreach_models.py -v
```

Expected: package/import failures.

- [ ] **Step 3: Implement `app/outreach/models.py`**

Define strict literals and models exactly once. Minimum contracts:

```python
ContactChannel = Literal[
    "PUBLISHED_VACANCY_EMAIL",
    "OFFICIAL_HR_EMAIL",
    "VERIFIED_RECRUITER",
    "MANUAL_FORM",
]
ContactVerificationStatus = Literal[
    "VERIFIED_DIRECT",
    "VERIFIED_OFFICIAL",
    "IDENTITY_VERIFIED_EMAIL_UNKNOWN",
    "VERIFIED_ENRICHED",
    "MANUAL_ONLY",
    "UNVERIFIED",
]
ContactSourceKind = Literal["VACANCY", "OFFICIAL_SITE", "APOLLO", "MANUAL"]
ContactResolutionStatus = Literal[
    "RESOLVED",
    "BLOCKED_NO_CONTACT",
    "MANUAL_ONLY",
    "REQUIRES_ENRICHMENT",
    "BLOCKED_POLICY",
]
DraftVerificationBasis = Literal[
    "CREATED_EXACT",
    "RECREATED_EXACT",
    "READBACK_EXACT",
    "UNVERIFIABLE",
]
ApprovalScope = Literal["SINGLE", "BATCH"]
ApprovalStatus = Literal["ACTIVE", "REVOKED", "EXPIRED"]
OutreachEventType = Literal[
    "PACKET_ACCEPTED",
    "CONTACT_RESOLVED",
    "OUTREACH_READY",
    "DRAFT_CREATED",
    "DRAFT_REPLACED",
    "APPROVED",
    "APPROVAL_INVALIDATED",
    "SEND_REQUESTED",
    "SEND_ATTEMPTED",
    "SENT",
    "SEND_FAILED",
    "MANUAL_ROUTE",
    "RESPONSE_OBSERVED",
]
```

Use one `StrictOutreachModel(BaseModel)` with `extra="forbid"` and one `_require_aware()` helper.

Define:

```python
class ContactPolicy(StrictOutreachModel):
    resolver_version: str = "contact-v1"
    priority: list[ContactChannel] = Field(
        default_factory=lambda: [
            "PUBLISHED_VACANCY_EMAIL",
            "OFFICIAL_HR_EMAIL",
            "VERIFIED_RECRUITER",
            "MANUAL_FORM",
        ]
    )
    max_recruiter_contacts_per_company_day: int = Field(default=2, ge=0)


class ContactCandidate(StrictOutreachModel):
    candidate_id: str
    opportunity_id: str
    channel: ContactChannel
    email: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    organization: str
    source_kind: ContactSourceKind
    source_ref: str
    confidence: float = Field(ge=0, le=1)
    verification_status: ContactVerificationStatus
    requires_paid_enrichment: bool = False
    discovered_at: datetime


class ContactResolution(StrictOutreachModel):
    opportunity_id: str
    selected_candidate_id: str | None = None
    channel: ContactChannel
    email: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    organization: str
    source_kind: ContactSourceKind
    source_ref: str
    confidence: float = Field(ge=0, le=1)
    verification_status: ContactVerificationStatus
    resolution_reason: str
    resolved_at: datetime
    resolver_version: str

    @model_validator(mode="after")
    def actionable_email_requires_verification(self):
        if self.email and self.verification_status in {"UNVERIFIED", "IDENTITY_VERIFIED_EMAIL_UNKNOWN"}:
            raise ValueError("actionable email requires verified contact provenance")
        return self


class ContactResolutionResult(StrictOutreachModel):
    status: ContactResolutionStatus
    resolution: ContactResolution | None = None
    candidates: list[ContactCandidate] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
```

Add `StretchPromotion`, `OutreachPolicy`, `OutreachClaim`, `OutreachBrief`, `OutreachPreparationResult`, `DraftAttachment`, `DraftSnapshot`, `ApprovalRequest`, `ApprovalRecord`, `SendRequest`, `SendAuthorizationResult`, `SendReceipt`, and `OutreachEvent` with the exact fields from the approved spec. Add validators so:

- all timestamps are timezone-aware;
- `DraftSnapshot` requires exactly one `CV` attachment whose SHA matches `cv_sha256`;
- batch approval requires `batch_manifest_sha256`, single approval forbids it;
- revoked/expired approvals cannot report `ACTIVE`;
- `SendReceipt.status` is always `SENT`.

Implementation detail required by the Gmail boundary: `DraftSnapshot.verification_basis` and `verified_at` are operational metadata and are excluded from `draft_sha256`.

- [ ] **Step 4: Implement `app/outreach/hashing.py`**

Reuse the existing canonical serializer rather than inventing another format:

```python
from app.cv.hashing import canonical_sha256


def draft_semantic_payload(snapshot: DraftSnapshot) -> dict:
    return {
        "opportunity_id": snapshot.opportunity_id,
        "brief_sha256": snapshot.brief_sha256,
        "application_packet_sha256": snapshot.application_packet_sha256,
        "reply_message_id": snapshot.reply_message_id,
        "to": sorted(address.casefold() for address in snapshot.to),
        "cc": sorted(address.casefold() for address in snapshot.cc),
        "bcc": sorted(address.casefold() for address in snapshot.bcc),
        "subject": snapshot.subject,
        "body_canonical": snapshot.body_canonical,
        "attachments": sorted(
            [attachment.model_dump(mode="json") for attachment in snapshot.attachments],
            key=lambda item: (item["role"], item["filename"], item["sha256"]),
        ),
        "cv_sha256": snapshot.cv_sha256,
        "content_type": snapshot.content_type,
    }


def draft_sha256(snapshot: DraftSnapshot) -> str:
    return canonical_sha256(draft_semantic_payload(snapshot))


def batch_manifest_sha256(draft_hashes: list[str]) -> str:
    return canonical_sha256(sorted(set(draft_hashes)))


def send_idempotency_key(
    *, opportunity_id: str, primary_recipient: str, packet_sha256: str, draft_hash: str
) -> str:
    return canonical_sha256(
        {
            "opportunity_id": opportunity_id,
            "primary_recipient": primary_recipient.casefold().strip(),
            "application_packet_sha256": packet_sha256,
            "draft_sha256": draft_hash,
        }
    )
```

Implement equivalent `brief_semantic_payload()` / `brief_sha256()` excluding `brief_id` and `created_at`.

- [ ] **Step 5: Run models/hash tests**

```bash
python -m pytest tests/test_outreach_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add app/outreach tests/test_outreach_models.py
git commit -m "feat: add outreach contracts and hashes"
```

---

### Task 3: Add Private SQLite Outreach Repository and Append-only Ledger

**Files:**
- Create: `app/outreach/repository.py`
- Create: `tests/test_outreach_repository.py`

**Interfaces:**
- Consumes: models from Task 2.
- Produces: `SQLiteOutreachRepository` implementing persistence, active approval lookup, receipt/idempotency lookup, duplicate-send queries, recruiter-contact daily counts, and ordered event history.

- [ ] **Step 1: Write failing repository tests**

Cover persistence across instances, idempotent snapshot saves, append-only events, one receipt per idempotency key, and no loss of historical success state:

```python
def test_receipt_idempotency_survives_repository_restart(tmp_path):
    path = tmp_path / "outreach.sqlite3"
    first = SQLiteOutreachRepository(path)
    first.initialize()
    first.save_send_receipt(_receipt("key-1"))

    second = SQLiteOutreachRepository(path)
    second.initialize()
    assert second.get_send_receipt_by_idempotency_key("key-1") is not None


def test_duplicate_receipt_key_cannot_create_second_success(tmp_path):
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    repo.save_send_receipt(_receipt("key-1", receipt_id="receipt-1"))
    existing = repo.save_send_receipt(_receipt("key-1", receipt_id="receipt-2"))
    assert existing.receipt_id == "receipt-1"


def test_events_are_append_only_and_ordered(tmp_path):
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    repo.append_event(_event("DRAFT_CREATED", "event-1", NOW))
    repo.append_event(_event("APPROVED", "event-2", NOW + timedelta(seconds=1)))
    assert [event.event_type for event in repo.list_events("opp-1")] == [
        "DRAFT_CREATED",
        "APPROVED",
    ]
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_outreach_repository.py -v
```

Expected: missing repository.

- [ ] **Step 3: Implement SQLite schema**

Use JSON payload tables plus indexed semantic keys, consistent with current repository patterns:

```sql
CREATE TABLE IF NOT EXISTS outreach_snapshots (
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_key)
);

CREATE TABLE IF NOT EXISTS outreach_events (
    event_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS send_receipts (
    receipt_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    sent_at TEXT NOT NULL
);
```

Add indexes on `opportunity_id`, event `(opportunity_id, occurred_at)`, and `sent_at`.

- [ ] **Step 4: Implement typed methods**

Required methods:

```python
initialize() -> None
save_contact_resolution(value: ContactResolution) -> ContactResolution
save_outreach_brief(value: OutreachBrief) -> OutreachBrief
save_draft_snapshot(value: DraftSnapshot) -> DraftSnapshot
save_approval(value: ApprovalRecord) -> ApprovalRecord
save_send_request(value: SendRequest) -> SendRequest
append_event(value: OutreachEvent) -> OutreachEvent
list_events(opportunity_id: str) -> list[OutreachEvent]
get_active_approval(draft_sha256: str, now: datetime) -> ApprovalRecord | None
get_send_receipt_by_idempotency_key(key: str) -> SendReceipt | None
save_send_receipt(value: SendReceipt) -> SendReceipt
has_successful_send_for_opportunity(opportunity_id: str) -> bool
count_recruiter_contacts_for_company_day(company: str, day: date) -> int
```

Store model JSON via `model_dump_json()` and revalidate with `model_validate_json()` on read. Never use pickle.

- [ ] **Step 5: Run repository tests**

```bash
python -m pytest tests/test_outreach_repository.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add app/outreach/repository.py tests/test_outreach_repository.py
git commit -m "feat: add outreach ledger repository"
```

---

### Task 4: Implement Deterministic Contact Resolution

**Files:**
- Create: `app/outreach/contact.py`
- Create: `tests/test_outreach_contact.py`

**Interfaces:**
- Consumes: `Opportunity`, `OpportunityEnrichment.application_contact_hints`, externally supplied `ContactCandidate` values, `ContactPolicy`, repository reader methods.
- Produces: `ContactResolutionService.resolve(...) -> ContactResolutionResult`.

- [ ] **Step 1: Write failing priority/fail-closed tests**

Required cases:

```python
def test_published_email_beats_official_hr_and_recruiter(): ...
def test_official_hr_beats_verified_recruiter(): ...
def test_verified_recruiter_with_unknown_email_returns_requires_enrichment(): ...
def test_unverified_email_candidate_is_never_actionable(): ...
def test_manual_form_is_returned_only_after_email_channels_fail(): ...
def test_no_contact_fails_closed_without_guessing(): ...
def test_existing_successful_send_blocks_new_initial_resolution(): ...
def test_recruiter_daily_company_cap_blocks_third_recruiter_contact(): ...
```

For the guessing regression, feed company `Example Labs` and no hints/candidates, then assert neither `jobs@example.test` nor `careers@example.test` appears anywhere in the result JSON.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_outreach_contact.py -v
```

- [ ] **Step 3: Implement `ContactResolutionService`**

Constructor:

```python
class ContactResolutionService:
    def __init__(self, *, id_factory: Callable[[], str] | None = None) -> None:
        self.id_factory = id_factory or (lambda: str(uuid4()))
```

Public method:

```python
def resolve(
    self,
    *,
    opportunity: Opportunity,
    enrichment: OpportunityEnrichment,
    candidates: list[ContactCandidate],
    policy: ContactPolicy,
    ledger: SQLiteOutreachRepository,
    now: datetime,
) -> ContactResolutionResult:
```

Behavior:

1. Require aware `now`.
2. If `ledger.has_successful_send_for_opportunity(opportunity.id)`, return `BLOCKED_POLICY` with privacy-safe code `already_sent`.
3. Convert each `PUBLISHED_EMAIL` radar hint into a `ContactCandidate` with `VERIFIED_DIRECT`, source `VACANCY`, and no paid enrichment.
4. Reject candidate opportunity IDs that do not match.
5. Filter actionable emails to statuses `VERIFIED_DIRECT`, `VERIFIED_OFFICIAL`, `VERIFIED_ENRICHED`.
6. Rank strictly by `policy.priority`, then confidence descending, then candidate ID ascending.
7. For recruiter identity with no email and `requires_paid_enrichment=True`, return `REQUIRES_ENRICHMENT`; do not fabricate email.
8. Before selecting a recruiter, enforce `policy.max_recruiter_contacts_per_company_day` using ledger count.
9. If only manual form remains, return `MANUAL_ONLY` with a resolution whose verification status is `MANUAL_ONLY` and email is `None`.
10. Otherwise return `BLOCKED_NO_CONTACT`.

- [ ] **Step 4: Run contact tests**

```bash
python -m pytest tests/test_outreach_contact.py tests/test_radar_application_contact.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add app/outreach/contact.py tests/test_outreach_contact.py
git commit -m "feat: resolve outreach contacts safely"
```

---

### Task 5: Prepare Evidence-bounded OutreachBriefs

**Files:**
- Create: `app/outreach/preparation.py`
- Create: `tests/test_outreach_preparation.py`

**Interfaces:**
- Consumes: `RadarAssessment`, V0.2B `ApplicationPacket`, `ContactResolution`, `OutreachPolicy`, optional `StretchPromotion`, actual local CV artifact.
- Produces: `OutreachPreparationService.prepare(...) -> OutreachPreparationResult` with a deterministic `OutreachBrief` or typed block.

- [ ] **Step 1: Write failing preparation tests**

Cover:

```python
def test_high_direct_email_prepares_outreach_brief(tmp_path): ...
def test_medium_prepares_automatically(tmp_path): ...
def test_stretch_without_promotion_blocks(tmp_path): ...
def test_stretch_with_explicit_promotion_can_prepare(tmp_path): ...
def test_packet_opportunity_mismatch_blocks(tmp_path): ...
def test_missing_cv_file_blocks(tmp_path): ...
def test_cv_hash_mismatch_blocks(tmp_path): ...
def test_unresolved_requirement_remains_gap_not_allowed_claim(tmp_path): ...
def test_allowed_claims_are_subset_of_packet_cv_claims(tmp_path): ...
def test_same_semantics_produce_same_brief_hash_despite_new_brief_id_and_time(tmp_path): ...
```

Use `tmp_path` to write fictional PDF bytes and SHA-256 them; do not use a real CV.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_outreach_preparation.py -v
```

- [ ] **Step 3: Implement `OutreachPolicy` defaults used by preparation**

In `models.py`, ensure:

```python
class OutreachPolicy(StrictOutreachModel):
    brief_version: str = "outreach-brief-v1"
    automatic_tiers: list[str] = Field(default_factory=lambda: ["HIGH", "MEDIUM"])
    max_allowed_claims: int = Field(default=6, ge=1)
    max_why_fit: int = Field(default=3, ge=1)
    tone_policy: str = "concise_professional"
    call_to_action_policy: str = "simple_next_step"
```

- [ ] **Step 4: Implement packet/tier/CV gates**

Helper rules:

```python
def _selected_tier(assessment: RadarAssessment) -> str | None:
    if assessment.selected_intent is not None:
        value = assessment.intent_tiers.get(assessment.selected_intent)
        if value is not None:
            return value
    return assessment.tier
```

Block if:

- radar eligibility is false;
- selected tier is outside automatic tiers and no valid stretch promotion exists;
- packet IDs/hash metadata mismatch the assessment opportunity;
- `Path(packet.cv_pdf_path)` does not exist;
- file SHA-256 differs from `packet.cv_sha256`;
- contact resolution has no verified email for the initial email path.

- [ ] **Step 5: Implement bounded claims and deterministic brief**

Allowed claim source is only `packet.cv_document.claims` whose `claim_id` is present in the document provenance map. Exclude candidate `identity`, `contact`, `location`, and `link` kinds from evidence bullets. Keep a maximum of `policy.max_allowed_claims` in stable document order.

Represent each allowed claim as:

```python
OutreachClaim(
    claim_id=claim.claim_id,
    text=claim.text,
    kind=claim.kind,
    fact_ids=packet.cv_document.provenance_map[claim.claim_id].fact_ids,
    evidence_ids=packet.cv_document.provenance_map[claim.claim_id].evidence_ids,
)
```

Set:

```python
why_fit = [claim.text for claim in allowed_claims[: policy.max_why_fit]]
strongest_evidence = allowed_claims[: policy.max_why_fit]
forbidden_claims = [f"Do not claim support for: {gap}" for gap in packet.unresolved_gaps]
unresolved_gaps = list(packet.unresolved_gaps)
```

Set `language` from `packet.cv_document.language`, `cv_filename = Path(packet.cv_pdf_path).name`, and `application_mode = assessment.enrichment.application_mode`.

Create with temporary zero hash, then replace with `brief_sha256(brief)`.

- [ ] **Step 6: Run preparation tests**

```bash
python -m pytest tests/test_outreach_preparation.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add app/outreach/preparation.py app/outreach/models.py tests/test_outreach_preparation.py
git commit -m "feat: prepare evidence bounded outreach briefs"
```

---

### Task 6: Build Exact Draft Snapshots and Human Approval Records

**Files:**
- Create: `app/outreach/draft.py`
- Create: `app/outreach/approval.py`
- Create: `tests/test_outreach_draft.py`
- Create: `tests/test_outreach_approval.py`

**Interfaces:**
- Consumes: external Gmail result metadata supplied by ChatGPT, known subject/body/recipient/attachment values, `OutreachBrief`, repository.
- Produces: exact `DraftSnapshot`, `ApprovalRecord`, batch manifest hash, approval invalidation/expiry checks.

- [ ] **Step 1: Write failing DraftSnapshot tests**

Required cases:

```python
def test_build_snapshot_hashes_exact_semantic_payload(): ...
def test_new_gmail_draft_id_preserves_hash_for_exact_replica(): ...
def test_subject_change_changes_hash(): ...
def test_body_change_changes_hash(): ...
def test_recipient_change_changes_hash(): ...
def test_reply_target_change_changes_hash(): ...
def test_attachment_filename_change_changes_hash(): ...
def test_attachment_hash_change_changes_hash(): ...
def test_unverifiable_basis_cannot_be_send_ready(): ...
```

- [ ] **Step 2: Implement `build_draft_snapshot()`**

Signature:

```python
def build_draft_snapshot(
    *,
    opportunity_id: str,
    brief_sha256_value: str,
    application_packet_sha256: str,
    provider_draft_id: str,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body: str,
    attachments: list[DraftAttachment],
    cv_sha256: str,
    content_type: str,
    reply_message_id: str | None,
    verification_basis: DraftVerificationBasis,
    now: datetime,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> DraftSnapshot:
```

Canonicalize line endings only:

```python
body_canonical = body.replace("\r\n", "\n").replace("\r", "\n")
```

Do not rewrite prose, whitespace inside lines, recipients, or subject.

Build with zero hash, compute `draft_sha256()`, then return copied final model.

- [ ] **Step 3: Run draft tests**

```bash
python -m pytest tests/test_outreach_draft.py -v
```

- [ ] **Step 4: Write failing approval tests**

Required cases:

```python
def test_single_approval_binds_exact_draft_hash(): ...
def test_batch_approval_requires_exact_manifest(): ...
def test_changed_draft_has_no_active_approval(): ...
def test_revoked_approval_blocks(): ...
def test_expired_approval_blocks(): ...
def test_approval_never_creates_send_request(): ...
```

- [ ] **Step 5: Implement `ApprovalService`**

Signature:

```python
class ApprovalService:
    def approve(
        self,
        *,
        draft_snapshot: DraftSnapshot,
        approval_request: ApprovalRequest,
        ledger: SQLiteOutreachRepository,
        now: datetime,
    ) -> ApprovalRecord:
```

Rules:

- request draft hash must equal snapshot hash;
- `UNVERIFIABLE` snapshot cannot be approved for automated send;
- single scope has no manifest;
- batch scope manifest must equal `batch_manifest_sha256(request.draft_sha256s)` and include current hash;
- save record + append `APPROVED` event;
- method returns only `ApprovalRecord`; it must not import or construct `SendRequest`.

Add:

```python
is_active(record: ApprovalRecord, *, now: datetime) -> bool
revoke(record: ApprovalRecord, *, revoked_at: datetime) -> ApprovalRecord
```

- [ ] **Step 6: Run draft + approval tests**

```bash
python -m pytest tests/test_outreach_draft.py tests/test_outreach_approval.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add app/outreach/draft.py app/outreach/approval.py tests/test_outreach_draft.py tests/test_outreach_approval.py
git commit -m "feat: add exact draft approval workflow"
```

---

### Task 7: Require Separate SendRequest, Enforce SendGate, and Record One Receipt

**Files:**
- Create: `app/outreach/send.py`
- Create: `tests/test_outreach_send.py`

**Interfaces:**
- Consumes: `DraftSnapshot`, active `ApprovalRecord`, fresh `SendRequest`, contact policy/resolution, repository state.
- Produces: `SendAuthorizationResult` and validated `SendReceipt` recording after provider success.

- [ ] **Step 1: Write failing send-gate tests**

Required cases:

```python
def test_valid_approval_without_send_request_blocks(): ...
def test_send_request_for_different_draft_hash_blocks(): ...
def test_send_request_for_different_approval_blocks(): ...
def test_unverifiable_draft_blocks(): ...
def test_expired_approval_blocks(): ...
def test_already_sent_idempotency_key_blocks_second_send(): ...
def test_valid_gate_returns_authorization_without_calling_provider(): ...
def test_failed_provider_attempt_is_not_sent(): ...
def test_successful_provider_receipt_records_exactly_once(): ...
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_outreach_send.py -v
```

- [ ] **Step 3: Implement `create_send_request()`**

```python
def create_send_request(
    *,
    opportunity_id: str,
    draft_sha256: str,
    approval_id: str,
    requested_by: str,
    now: datetime,
    batch_manifest_sha256: str | None = None,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> SendRequest:
```

This function has no default/implicit call site in preparation or approval.

- [ ] **Step 4: Implement `SendGate.validate()`**

Signature from spec:

```python
class SendGate:
    def validate(
        self,
        *,
        draft_snapshot: DraftSnapshot,
        approval_record: ApprovalRecord | None,
        send_request: SendRequest | None,
        contact_resolution: ContactResolution,
        ledger: SQLiteOutreachRepository,
        policy: OutreachPolicy,
        now: datetime,
    ) -> SendAuthorizationResult:
```

Validation order must be deterministic and fail closed:

1. missing request -> `send_request_missing`;
2. missing approval -> `approval_missing`;
3. request draft/approval mismatch -> `send_request_invalid`;
4. inactive/revoked/expired approval -> `approval_invalid` / `approval_expired`;
5. draft hash does not recompute -> `draft_changed`;
6. verification basis `UNVERIFIABLE` -> `draft_unverifiable`;
7. draft recipient differs from contact resolution email -> `outreach_policy_blocked`;
8. CV attachment hash differs from snapshot CV hash -> `draft_changed`;
9. compute idempotency key;
10. existing receipt for key -> `already_sent`;
11. otherwise return `authorized=True` with key.

No provider import is permitted in `app/outreach/send.py`.

- [ ] **Step 5: Implement provider receipt validation/recording**

Function:

```python
def record_successful_send(
    *,
    authorization: SendAuthorizationResult,
    approval: ApprovalRecord,
    send_request: SendRequest,
    draft_snapshot: DraftSnapshot,
    provider_message_id: str,
    provider_thread_id: str | None,
    ledger: SQLiteOutreachRepository,
    now: datetime,
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> SendReceipt:
```

Reject empty provider message ID. Save receipt first using unique idempotency key, then append `SENT` event. A duplicate returns the existing receipt.

Provider failure is represented by a separate `record_send_failure(...)` event helper; it must never create a `SendReceipt`.

- [ ] **Step 6: Run send tests**

```bash
python -m pytest tests/test_outreach_send.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add app/outreach/send.py tests/test_outreach_send.py
git commit -m "feat: gate and record explicit outreach sends"
```

---

### Task 8: Add Thin Outreach Orchestration, Release Contract, Privacy Guard, and Full Integration Test

**Files:**
- Create: `app/outreach/service.py`
- Create: `tests/test_outreach_service.py`
- Create: `tests/test_outreach_release_contract.py`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `.github/workflows/tests.yml`
- Modify: `docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md` (`Status: approved` only)

**Interfaces:**
- Consumes: all Tasks 1-7.
- Produces: one end-to-end deterministic core service for the direct-email path, package prerelease `0.2.0c1`, documented operator boundary, CI privacy contract.

- [ ] **Step 1: Write failing service integration test**

Use fictional opportunity/CV bytes and a temporary SQLite database. The test must execute the full deterministic core around an externally simulated Gmail operation:

```python
def test_direct_email_application_flow_requires_approval_and_separate_send(tmp_path):
    # 1. Radar assessment contains typed published email.
    # 2. Existing fictional ApplicationPacket points to tmp_path CV bytes.
    # 3. service.prepare_outreach(...) returns OUTREACH_READY.
    # 4. test simulates ChatGPT/Gmail by supplying provider_draft_id plus exact payload.
    # 5. service.register_draft(...) returns exact DraftSnapshot.
    # 6. service.approve_draft(...) returns ApprovalRecord only.
    # 7. send gate without send request is blocked.
    # 8. service.request_send(...) creates explicit SendRequest.
    # 9. service.authorize_send(...) succeeds.
    # 10. simulated provider message ID is recorded once.
    # 11. a second authorize/record path is blocked or returns the existing receipt.
```

Also add:

```python
def test_recreated_exact_draft_can_use_same_approval_hash(tmp_path):
    # Draft A and recreated Draft B use different provider IDs but exact same
    # recipients/body/subject/attachment filename+hash, so semantic hash is equal.
```

- [ ] **Step 2: Implement thin `OutreachService`**

Constructor receives dependencies; it does not instantiate Gmail/Apollo clients:

```python
class OutreachService:
    def __init__(
        self,
        *,
        repository: SQLiteOutreachRepository,
        contact_service: ContactResolutionService | None = None,
        preparation_service: OutreachPreparationService | None = None,
        approval_service: ApprovalService | None = None,
        send_gate: SendGate | None = None,
    ) -> None:
        ...
```

Expose only orchestration methods:

```python
prepare_outreach(...) -> OutreachPreparationResult
register_draft(...) -> DraftSnapshot
approve_draft(...) -> ApprovalRecord
request_send(...) -> SendRequest
authorize_send(...) -> SendAuthorizationResult
record_send_success(...) -> SendReceipt
```

Each successful transition appends the corresponding ledger event. No method performs external provider I/O.

Operator rule for Gmail environments without exact draft readback: before `authorize_send`, ChatGPT may create a fresh Gmail draft from the approved canonical snapshot and call `register_draft(... verification_basis="RECREATED_EXACT")`. If its semantic hash is identical, the existing approval remains valid even though the provider draft ID changes.

- [ ] **Step 3: Run integration tests**

```bash
python -m pytest tests/test_outreach_service.py -v
```

Expected: PASS.

- [ ] **Step 4: Write release/privacy contract tests**

`tests/test_outreach_release_contract.py` must assert:

```python
def test_package_version_is_v02c_prerelease():
    assert project_version() == "0.2.0c1"


def test_readme_documents_operator_boundary():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "V0.2C" in text
    assert "does not create Gmail drafts automatically" in text
    assert "Approval is not a send command" in text


def test_outreach_private_paths_are_ignored_and_ci_guarded():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert "state/outreach.local.sqlite3" in gitignore
    assert "artifacts/applications/" in gitignore
    assert "state/outreach.local.sqlite3" in workflow
```

Preserve historical `.gitignore` rules exactly; append only V0.2C-specific private paths.

- [ ] **Step 5: Update prerelease/version/docs**

Change:

```toml
version = "0.2.0c1"
```

README V0.2C section must document:

```text
ApplicationPacket
-> verified contact
-> OutreachBrief
-> user-requested Gmail draft
-> exact draft hash
-> explicit approval
-> separate explicit send request
-> idempotent send receipt
```

State explicitly:

- Opportunity OS does not create Gmail drafts automatically.
- Approval is not a send command.
- No Gmail/Apollo credentials live in the repo.
- Apollo enrichment remains optional and explicit-credit-confirmed.

Change spec header from `Status: review` to `Status: approved` with no other semantic spec edits in this task.

- [ ] **Step 6: Expand privacy guard without weakening existing rules**

Append to `.gitignore`:

```text
state/outreach.local.sqlite3
artifacts/applications/*/outreach/
```

Expand CI guard with:

```bash
'state/outreach.local.sqlite3' \
'artifacts/applications/**/outreach/**' \
```

Keep all previous forbidden patterns (`.env`, local profiles, local evidence, application artifacts, `*.pdf`, `*.docx`).

- [ ] **Step 7: Run release tests**

```bash
python -m pytest tests/test_outreach_release_contract.py -v
```

Expected: PASS.

- [ ] **Step 8: Run full release verification**

Run exactly:

```bash
python -m pytest -v
python -m compileall app
git diff --check origin/main...HEAD
```

Then run the same privacy query as CI locally:

```bash
forbidden="$(git ls-files -- \
  '.env' \
  'profile.local.yaml' \
  'sources.local.yaml' \
  'profile/master_facts.local.yaml' \
  'profile/evidence_catalog.local.yaml' \
  'state/outreach.local.sqlite3' \
  'artifacts/applications/**' \
  '*.pdf' \
  '*.docx')"
test -z "$forbidden"
```

Expected: all tests pass; compile succeeds; diff check empty; forbidden variable empty. Any failure stops release work.

- [ ] **Step 9: Commit Task 8**

```bash
git add app/outreach/service.py tests/test_outreach_service.py tests/test_outreach_release_contract.py README.md pyproject.toml .gitignore .github/workflows/tests.yml docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md
git commit -m "feat: complete V0.2C email outreach core"
```

---

## Execution Order and Checkpoints

Do not parallelize Tasks 1-3 because later contracts depend on earlier names. Tasks 4 and 5 both depend on Tasks 1-3 but should still be reviewed independently before workflow-state work. Tasks 6 and 7 must remain separate so reviewers can reject approval semantics without conflating them with send semantics.

Checkpoint after Task 5:

```text
Radar email -> ContactResolution -> OutreachBrief
```

At this point Opportunity OS can prepare real outreach packets but cannot create/approve/send drafts.

Checkpoint after Task 7:

```text
DraftSnapshot -> ApprovalRecord -> explicit SendRequest -> SendGate -> SendReceipt
```

At this point all safety semantics exist.

Checkpoint after Task 8:

```text
complete deterministic V0.2C direct-email core + private ledger + release contract
```

Then ChatGPT can operate the external side with connected Gmail:

1. load exact `OutreachBrief` + `ApplicationPacket`;
2. write evidence-bounded copy;
3. create Gmail draft with exact CV;
4. register known semantic draft snapshot;
5. present draft for review;
6. record explicit approval;
7. wait for separate explicit send instruction;
8. if exact Gmail readback is unavailable, recreate an exact semantic replica from the approved snapshot and register it as `RECREATED_EXACT`;
9. validate SendGate;
10. call Gmail `send_draft` only after authorization;
11. record provider receipt.

Apollo/recruiter enrichment is intentionally not required to pass the first real-use milestone. It plugs into Task 4 later through `ContactCandidate` without changing approval/send contracts.
