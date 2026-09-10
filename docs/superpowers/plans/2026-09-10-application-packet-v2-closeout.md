# ApplicationPacket v2 Close-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make newly prepared CV application packets fully auditable by persisting versioned strategy/layout/narrative/visual/ATS state while preserving historical packet compatibility.

**Architecture:** `ApplicationPacket` gains a schema version and a backward-compatible optional v2 audit bundle. `CVPreparationService` emits only v2 packets and persists the exact strategy/layout/QA objects that passed the final pipeline. Packet hashing includes the new authoritative v2 fields while continuing to exclude runtime identity/time/path values.

**Tech Stack:** Python 3.12/3.13, Pydantic v2, pytest, existing Opportunity-OS CV models and GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-10-application-packet-v2-closeout-design.md`

## Global Constraints

- Branch from exact verified base `c0532fd9e163f73b7ef18d3a5b199a8d3b97800a`.
- Do not modify CAREER ranking, evidence/provenance, recruiter reducer, renderer selection, Gmail/outreach, or automatic external actions.
- Historical packets without `packet_schema_version` must remain valid as v1.
- New `CVPreparationService.prepare()` success packets must emit `application-packet-v2`.
- V2 stores exact authoritative strategy/layout/narrative/visual/ATS values that passed the pipeline.
- V2 hashing must include all new audit fields and must continue excluding application id, creation time, and PDF path.
- TDD is mandatory: observe RED before implementation for each behavioral task.
- Do not merge the final PR without explicit human approval.

---

### Task 1: ApplicationPacket v2 model contract

**Files:**
- Modify: `app/cv/models.py`
- Create: `tests/test_application_packet_v2.py`

**Interfaces:**
- Consumes: existing `ApplicationPacket`, `CVStrategy`, `NarrativeQAResult`, `VisualQAResult`, `ATSRoundTripQAResult`.
- Produces: `packet_schema_version`, typed v2 audit fields, and v1/v2 validation invariants.

- [ ] **Step 1: Write failing model-contract tests**

Create `tests/test_application_packet_v2.py` using `sample_packet()` from `tests/test_cv_models.py`. Tests must prove:

```python
def test_historical_packet_without_schema_version_restores_as_v1():
    payload = sample_packet().model_dump(mode="json", exclude_none=True)
    payload.pop("packet_schema_version", None)
    restored = ApplicationPacket.model_validate(payload)
    assert restored.packet_schema_version == "application-packet-v1"


def test_v2_requires_complete_audit_bundle():
    payload = sample_packet().model_dump(mode="json", exclude_none=True)
    payload["packet_schema_version"] = "application-packet-v2"
    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)


def test_v2_rejects_strategy_version_mismatch():
    payload = complete_v2_payload()
    payload["strategy_version"] = "wrong-version"
    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)


def test_v2_rejects_layout_identity_mismatch():
    payload = complete_v2_payload()
    payload["layout_profile_id"] = "operations_clean"
    with pytest.raises(ValidationError):
        ApplicationPacket.model_validate(payload)
```

`complete_v2_payload()` must build real typed fixture data using `CVStrategy`, `NarrativeQAResult`, `VisualQAResult`, and the existing ATS QA fixture pattern. Do not use arbitrary dictionaries for the success case.

- [ ] **Step 2: Run tests and verify RED**

Run the repository test workflow on the tests-only commit. Expected failures must be limited to missing v2 fields/validation behavior; existing tests must remain green.

- [ ] **Step 3: Implement the minimal v2 model contract**

In `app/cv/models.py` add:

```python
ApplicationPacketSchemaVersion = Literal[
    "application-packet-v1",
    "application-packet-v2",
]
```

and fields conceptually equivalent to:

```python
packet_schema_version: ApplicationPacketSchemaVersion = "application-packet-v1"
strategy_version: str | None = None
strategy: Any | None = None
narrative_policy_version: str | None = None
layout_profile_id: str | None = None
layout_profile_version: str | None = None
narrative_qa: Any | None = None
visual_qa: Any | None = None
```

Use lazy `field_validator(..., mode="before")` imports to validate `strategy` as `CVStrategy`, `narrative_qa` as `NarrativeQAResult`, and `visual_qa` as `VisualQAResult`, matching the existing lazy typed validation pattern for `recruiter_document` and `ats_qa`.

Extend `validate_packet_contracts()` so:

```text
v1: new strategy/layout/narrative/visual fields must all be absent; existing ATS pair may remain present for compatibility.
v2: every new audit field plus the ATS pair must be present.
strategy_version == strategy.strategy_version.
layout_profile_id == the persisted selected profile id represented by the packet fields.
layout_profile_version is non-empty and versioned.
narrative_qa.valid, visual_qa.valid, ats_qa.valid are true.
ats_policy_version == ats_qa.policy_version.
```

The layout profile object itself is not persisted, so id/version validity is enforced by service integration plus supported-value typing where available; no renderer behavior changes.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run `tests/test_application_packet_v2.py`, `tests/test_cv_models.py`, and `tests/test_cv_service_ats_roundtrip.py`. Expected: all pass.

- [ ] **Step 5: Commit**

Commit message:

```text
feat(cv): add backward-compatible ApplicationPacket v2 contract
```

---

### Task 2: Persist authoritative final pipeline state

**Files:**
- Modify: `app/cv/service.py`
- Create: `tests/test_cv_application_packet_v2_service.py`

**Interfaces:**
- Consumes: Task 1 `ApplicationPacket` v2 fields; existing `strategy`, `NarrativePolicy`, selected `LayoutProfile`, `NarrativeQAResult`, `VisualQAResult`, and `ATSRoundTripQAResult` values already created by `CVPreparationService`.
- Produces: new successful packets with a complete v2 audit bundle.

- [ ] **Step 1: Write failing service integration tests**

Add tests that call the real service fixture path and assert:

```python
assert result.packet.packet_schema_version == "application-packet-v2"
assert result.packet.strategy == captured_strategy
assert result.packet.strategy_version == captured_strategy.strategy_version
assert result.packet.narrative_policy_version == service.narrative_policy.version
assert result.packet.layout_profile_id == selected_profile.id
assert result.packet.layout_profile_version == selected_profile.version
assert result.packet.narrative_qa.valid
assert result.packet.visual_qa.valid
assert result.packet.ats_qa.valid
```

Add a reduction-path regression using a deterministic QA double that forces one existing reducible failure, then succeeds. Record narrative QA evaluations and assert the packet stores the QA result from the final reduced recruiter document, not the initial one.

- [ ] **Step 2: Run tests and verify RED**

Expected failure: current service emits no v2 schema/audit fields and does not retain final narrative QA state.

- [ ] **Step 3: Implement minimal service persistence**

In `CVPreparationService.prepare()`:

```python
final_narrative_result = narrative_result
```

Whenever a reduced recruiter document is accepted after `reduced_narrative_result` validation:

```python
final_narrative_result = reduced_narrative_result
```

Require `final_narrative_result` alongside final render/structural/visual/ATS results at the success boundary.

Populate the packet with:

```python
packet_schema_version="application-packet-v2",
strategy_version=strategy.strategy_version,
strategy=strategy,
narrative_policy_version=self.narrative_policy.version,
layout_profile_id=selected_layout_profile.id,
layout_profile_version=selected_layout_profile.version,
narrative_qa=final_narrative_result,
visual_qa=final_visual_result,
ats_policy_version=self.ats_policy.version,
ats_qa=final_ats_result,
```

Do not alter ranking, evidence selection, provenance, reducer rules, renderer selection, or QA thresholds.

- [ ] **Step 4: Run focused service tests and verify GREEN**

Run the new service tests plus `tests/test_cv_service.py`, `tests/test_cv_service_ats_roundtrip.py`, narrative QA/reduction tests, and renderer tests. Expected: all pass.

- [ ] **Step 5: Commit**

Commit message:

```text
feat(cv): persist final strategy layout and QA state
```

---

### Task 3: Hash v2 authoritative audit state

**Files:**
- Modify: `app/cv/service.py`
- Create or extend: `tests/test_cv_application_packet_v2_service.py`

**Interfaces:**
- Consumes: complete v2 packet emitted by Task 2.
- Produces: deterministic packet hash sensitive to all v2 authoritative fields.

- [ ] **Step 1: Write failing hash sensitivity tests**

Construct two otherwise-identical v2 packets/preparations and vary one authoritative component at a time. At minimum prove hash changes for:

```text
strategy
narrative_policy_version
layout_profile_id or layout_profile_version
narrative_qa
visual_qa
ats_qa
```

Retain the existing test proving application id, `created_at`, and PDF path do not change the packet hash.

- [ ] **Step 2: Run tests and verify RED**

Expected: new fields that are absent from `_packet_content_payload()` do not yet affect the hash.

- [ ] **Step 3: Extend `_packet_content_payload()`**

Include:

```python
"packet_schema_version": packet.packet_schema_version,
"strategy_version": packet.strategy_version,
"strategy": packet.strategy.model_dump(mode="json") if packet.strategy else None,
"narrative_policy_version": packet.narrative_policy_version,
"layout_profile_id": packet.layout_profile_id,
"layout_profile_version": packet.layout_profile_version,
"narrative_qa": packet.narrative_qa.model_dump(mode="json") if packet.narrative_qa else None,
"visual_qa": packet.visual_qa.model_dump(mode="json") if packet.visual_qa else None,
```

Keep the existing ATS payload and all existing semantic fields. Do not add `application_id`, `created_at`, or `cv_pdf_path`.

- [ ] **Step 4: Run hash tests and verify GREEN**

Expected: all v2 sensitivity tests pass and the runtime-only exclusion regression remains green.

- [ ] **Step 5: Commit**

Commit message:

```text
feat(cv): hash ApplicationPacket v2 audit state
```

---

### Task 4: Close the architecture documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-09-cv-strategy-narrative-design.md`
- Modify: `README.md` only if the existing architecture summary needs the packet-v2 boundary stated explicitly.
- Modify: `tests/test_cv_release_contract.py`

**Interfaces:**
- Consumes: completed Tasks 1–3 and previously merged JSON Resume, optional ReportLab renderer, Visual QA, and ATS round-trip QA.
- Produces: repository documentation that describes the implemented architecture without vendor-ATS overclaiming.

- [ ] **Step 1: Write/update release-contract tests**

Require the architecture spec to state an implemented status and preserve the phrases/concepts:

```text
ApplicationPacket v2
recoverability proxy
RenderCV/Typst remains the default renderer
optional human-first renderer
```

The release contract must reject language claiming guaranteed commercial ATS ranking or vendor emulation.

- [ ] **Step 2: Run release-contract test and verify RED if documentation is stale**

Expected: failure because the original spec still says proposed and does not yet record packet-v2 completion.

- [ ] **Step 3: Update documentation minimally**

Change original architecture status to implemented and add a concise implementation-status section recording:

```text
strategy/narrative/layout/visual/ATS authoritative gates implemented
JSON Resume export implemented
ReportLab human-first renderer implemented as optional; RenderCV/Typst remains default
ApplicationPacket v2 implements the auditability/hash close-out
ATS round-trip QA remains a recoverability proxy, not a commercial ATS guarantee
```

- [ ] **Step 4: Run release-contract tests and verify GREEN**

Expected: pass.

- [ ] **Step 5: Commit**

Commit message:

```text
docs(cv): close strategy narrative architecture spec
```

---

### Task 5: Full verification and PR

**Files:**
- No production changes unless verification reveals a scoped defect.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: reviewable PR with fresh CI evidence; no merge.

- [ ] **Step 1: Revalidate current `main` and compare branch**

Confirm the branch still descends from the intended base or merge current `main` forward if it advanced. Never force-push or silently discard concurrent work.

- [ ] **Step 2: Run full GitHub Actions verification**

Require success for:

```text
pytest
compile application
feature diff whitespace
private-files guard
recruiter visual previews
build offline runtime Python 3.12
build offline runtime Python 3.13
verify offline runtime Python 3.12
verify offline runtime Python 3.13
```

- [ ] **Step 3: Review final diff against non-goals**

Confirm no changes under ranking/scoring, evidence/provenance semantics, reducer behavior, renderer selection, Gmail/outreach, or automatic sending.

- [ ] **Step 4: Open PR against `main`**

Title:

```text
feat: add ApplicationPacket v2 auditability close-out
```

PR body must summarize v1 compatibility, exact persisted v2 fields, final-state semantics after reduction, hash coverage, architecture-spec closure, and fresh CI evidence.

- [ ] **Step 5: Leave PR unmerged**

Do not enable auto-merge and do not merge until explicit human approval is received.
