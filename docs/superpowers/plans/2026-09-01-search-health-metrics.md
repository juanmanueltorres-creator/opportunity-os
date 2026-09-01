# Opportunity OS Search Health Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, provenance-aware Search Health report that combines native Opportunity OS state with explicitly imported historical observations without turning missing history into false zeroes.

**Architecture:** Add a focused `app.metrics` package. Native repositories/artifacts are read without creating missing databases; reconstructed history lives in a separate private SQLite store; both are normalized into typed metric facts; reconciliation only collapses facts that share an exact anchor, with native evidence taking precedence; projection then emits typed counts, conversion cohorts and `COMPLETE/PARTIAL/UNKNOWN` coverage through a CLI and aggregate JSON report.

**Tech Stack:** Python 3.12+, Pydantic v2, stdlib `sqlite3`, stdlib `argparse`, pytest. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-08-31-search-health-metrics-design.md`

## Global Constraints

- Initial dogfood reporting window starts at `2026-08-01` and ends at the requested report as-of time.
- `native ledger != historical reconstruction`; historical backfill never fabricates `OutreachEvent`, `SendReceipt` or `RelationshipEvent` rows.
- Exact evidence precedence is `native confirmed fact > imported provider evidence > manual historical assertion > unknown`.
- `UNKNOWN` is never silently converted to zero.
- Metrics are read-only over operational state: no apply, approval, send, relationship mutation, Gmail import into Relationship Memory, or opportunity-status mutation.
- Historical HIGH/MEDIUM qualification is never recomputed with current scoring code and presented as historical truth.
- V1 output is CLI + aggregate JSON only: no FastAPI metrics endpoint, web dashboard, multi-user analytics, productivity score or causal strategy ranking.
- Historical Gmail evidence is selected/authorized input; no mailbox-wide synchronization is introduced.
- Private history may retain exact reconciliation identifiers locally, but aggregate JSON contains no provider message/thread IDs, contact names, email addresses, subjects, bodies, company-specific private notes or credentials.
- Historical event certainty and linkage certainty remain separate as `event_confidence` and `link_confidence`, each bounded to `[0, 1]`.
- No fuzzy company-name, subject-similarity or nearest-timestamp matching is allowed for deduplication.
- Missing optional source paths do not create databases/directories as a side effect; they degrade coverage and emit bounded warnings.
- `opportunities_observed` and `opportunities_new` intentionally have the same value in V1 because the current opportunity repository persists one canonical first observation and does not persist gross duplicate observations.
- Fixed source state + fixed report window + fixed `--as-of` produce deterministic metric values and byte-stable JSON.
- Real August history, real Gmail evidence and the operator's generated Search Health output remain private/untracked.

---

## File Map

### New production files

- `app/metrics/__init__.py` — package exports only; no side effects.
- `app/metrics/models.py` — report window, coverage, count/ratio, source-summary and Search Health contracts.
- `app/metrics/history.py` — strict historical-observation/import models plus private SQLite history repository.
- `app/metrics/sources.py` — read-only adapters over Opportunity DB, ApplicationPacket files, Outreach DB, Relationship DB, optional Radar evidence and historical DB.
- `app/metrics/projection.py` — normalized facts, exact reconciliation, coverage propagation and Search Health projection.
- `app/metrics/import_history.py` — explicit private manifest -> historical SQLite CLI; the only V1 history write entrypoint.
- `app/metrics/report.py` — Search Health CLI, human rendering and aggregate JSON output.

### New tests

- `tests/test_metrics_models.py`
- `tests/test_metrics_history.py`
- `tests/test_metrics_sources.py`
- `tests/test_metrics_reconciliation.py`
- `tests/test_metrics_projection.py`
- `tests/test_metrics_report_cli.py`
- `tests/test_metrics_release_contract.py`

### Existing files modified only where required

- `.gitignore` — ignore Search Health private/generated artifacts.
- `.github/workflows/tests.yml` — strengthen tracked-private-file guard.
- `README.md` — describe Search Health only after real dogfood acceptance.
- `ROADMAP.md` — mark the reporting slice implemented only after acceptance evidence exists.

Do not modify `app/main.py`, FastAPI routes, Radar scoring, CV semantic authority, Outreach send gates, Relationship projection rules, Gmail read behavior, or existing operational repository write semantics.

---

### Task 1: Search Health Report Contracts

**Files:**
- Create: `app/metrics/__init__.py`
- Create: `app/metrics/models.py`
- Create: `tests/test_metrics_models.py`

**Interfaces:**
- Produces: `Coverage`, `ReportWindow`, `CountMetric`, `RatioMetric`, `SearchHealthCounts`, `SearchHealthRatios`, `CoverageSummary`, `SourceSummary`, `SearchHealthReport`.
- Consumes: timezone-aware `datetime`; no repository dependency.

- [ ] **Step 1: Write failing model tests**

Create `tests/test_metrics_models.py` with these core cases:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.metrics.models import RatioMetric, ReportWindow

UTC = timezone.utc


def test_report_window_rejects_reverse_range():
    with pytest.raises(ValidationError):
        ReportWindow(
            start=datetime(2026, 8, 2, tzinfo=UTC),
            end=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_unknown_ratio_keeps_observed_numbers_without_fabricating_zero():
    metric = RatioMetric(
        name="send_to_reply_rate",
        value=None,
        numerator=2,
        denominator=5,
        coverage="PARTIAL",
        basis=["historical_gmail"],
        warnings=["reply coverage incomplete"],
    )
    assert metric.value is None
    assert metric.denominator == 5


def test_zero_denominator_cannot_publish_numeric_ratio():
    with pytest.raises(ValidationError):
        RatioMetric(
            name="send_to_reply_rate",
            value=0.0,
            numerator=0,
            denominator=0,
            coverage="COMPLETE",
            basis=["native_outreach"],
        )
```

Also test timezone-awareness rejection, ratio bounds `[0, 1]`, non-negative counts, exact `report_version="search-health-v1"`, and strict extra-field rejection.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_models.py`

Expected: FAIL because `app.metrics.models` does not exist.

- [ ] **Step 3: Implement strict Pydantic contracts**

Use `ConfigDict(extra="forbid")` and this exact coverage contract:

```python
Coverage = Literal["COMPLETE", "PARTIAL", "UNKNOWN"]

class CountMetric(StrictMetricsModel):
    name: str = Field(min_length=1)
    value: int | None = Field(default=None, ge=0)
    coverage: Coverage
    basis: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class RatioMetric(StrictMetricsModel):
    name: str = Field(min_length=1)
    value: float | None = Field(default=None, ge=0, le=1)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    coverage: Coverage
    basis: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ratio(self):
        if self.denominator == 0 and self.value is not None:
            raise ValueError("zero denominator requires unknown ratio value")
        if self.value is not None:
            expected = self.numerator / self.denominator
            if abs(self.value - expected) > 1e-9:
                raise ValueError("ratio value must match numerator/denominator")
        return self
```

`SearchHealthCounts` exposes exactly: `opportunities_observed`, `opportunities_new`, `qualified_high`, `qualified_medium`, `packets_prepared`, `drafts_verified`, `confirmed_sends`, `replies_observed`, `processes_opened`, `processes_closed`.

`SearchHealthRatios` exposes exactly: `qualification_rate`, `draft_to_send_rate`, `send_to_reply_rate`, `reply_to_process_rate`.

`SearchHealthReport` contains `report_version`, `generated_at`, `window`, `counts`, `ratios`, `coverage`, `warnings`, `source_summary`.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_metrics_models.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/metrics/__init__.py app/metrics/models.py tests/test_metrics_models.py
git commit -m "feat: add search health report contracts"
```

---

### Task 2: Private Historical Observation Store and Strict Import

**Files:**
- Create: `app/metrics/history.py`
- Create: `app/metrics/import_history.py`
- Create: `tests/test_metrics_history.py`
- Modify: `.gitignore`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: explicit private JSON `HistoricalImportManifest` with normalized evidence only.
- Produces: `HistoricalObservation`, `HistoricalImportBatch`, `HistoricalImportManifest`, `SQLiteHistoricalRepository`, `import_manifest(...)`, and CLI `python -m app.metrics.import_history`.
- Persists only: `state/history.local.sqlite3` by default.

- [ ] **Step 1: Write RED history-model tests**

Use a complete explicit payload so the test itself contains no hidden fixture assumption:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.metrics.history import HistoricalObservation

UTC = timezone.utc

BASE = {
    "observation_id": "hist-reply-1",
    "kind": "REPLY_OBSERVED",
    "opportunity_id": None,
    "account_id": None,
    "company": "Example Labs",
    "role": None,
    "occurred_at": datetime(2026, 8, 20, tzinfo=UTC),
    "observed_at": datetime(2026, 8, 31, tzinfo=UTC),
    "provenance": "IMPORTED_GMAIL",
    "source_ref": "gmail-message-1",
    "provider_message_id": "m-1",
    "provider_thread_id": "t-1",
    "event_confidence": 1.0,
    "link_confidence": 0.0,
    "reconstruction_note": "provider-confirmed reply; opportunity unmatched",
}


def test_event_certainty_is_separate_from_link_certainty():
    observation = HistoricalObservation.model_validate(BASE)
    assert observation.event_confidence == 1.0
    assert observation.link_confidence == 0.0


def test_history_model_rejects_raw_body_field():
    with pytest.raises(ValidationError):
        HistoricalObservation.model_validate({**BASE, "body": "private mail body"})
```

Add tests for strict rejection of `subject`, `snippet`, token/credential-like extra fields, naive datetimes, confidence outside `[0,1]`, and oversized reconstruction notes.

- [ ] **Step 2: Write RED repository/import tests**

Prove: identical observation import is idempotent; same `observation_id` with changed semantics fails closed; identical batch import is idempotent; conflicting batch ID fails closed; the manifest is fully validated before DB initialization; a read against a missing history DB does not create it.

- [ ] **Step 3: Run RED**

Run: `pytest -q tests/test_metrics_history.py`

Expected: FAIL on missing history contracts/repository.

- [ ] **Step 4: Implement strict history types**

Use exact literals:

```python
HistoricalKind = Literal[
    "DRAFT_OBSERVED",
    "SEND_OBSERVED",
    "REPLY_OBSERVED",
    "PROCESS_OPENED_OBSERVED",
    "PROCESS_CLOSED_OBSERVED",
]
HistoricalProvenance = Literal["IMPORTED_GMAIL", "MANUAL_ASSERTION"]
SelectionScope = Literal["SELECTED_THREADS", "ALL_DECLARED_OUTREACH_THREADS"]
```

`HistoricalImportBatch` contains: `batch_id`, `provider`, `window_start`, `window_end`, `selection_scope`, `selected_message_count`, `selected_thread_count`, `completed_at`, `complete_for_declared_scope`.

- [ ] **Step 5: Implement private SQLite schema and exact conflict handling**

```sql
CREATE TABLE historical_observations (
    observation_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE historical_import_batches (
    batch_id TEXT PRIMARY KEY,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
```

Existing IDs deserialize back to typed models. Return the existing row only on semantic equality; otherwise raise `ValueError("historical observation_id conflict")` or `ValueError("historical batch_id conflict")`.

- [ ] **Step 6: Implement explicit import CLI**

Canonical private command:

```bash
python -m app.metrics.import_history \
  --manifest state/history-import-2026-08.local.json \
  --history-db state/history.local.sqlite3
```

Validate the whole JSON manifest before `initialize()`. Print only batch ID plus inserted/existing counts; never echo observations/provider identifiers.

- [ ] **Step 7: Strengthen ignore and CI privacy guards**

Append to `.gitignore`:

```text
artifacts/metrics/
state/history.local.sqlite3
state/history.local.sqlite3-*
state/history-import*.local.json
```

Add those same path families to the workflow's existing `git ls-files` forbidden set.

- [ ] **Step 8: Run GREEN**

```bash
pytest -q tests/test_metrics_history.py
git diff --check
```

Expected: PASS and no tracked private artifact.

- [ ] **Step 9: Commit**

```bash
git add app/metrics/history.py app/metrics/import_history.py tests/test_metrics_history.py .gitignore .github/workflows/tests.yml
git commit -m "feat: add private historical observation store"
```

---

### Task 3: Typed Read-Only Metric Sources

**Files:**
- Create: `app/metrics/sources.py`
- Create: `tests/test_metrics_sources.py`

**Interfaces:**
- Consumes: `ReportWindow`; paths to Opportunity DB, Outreach DB, Relationship DB, history DB, applications root and optional Radar evidence root.
- Produces: `SourceRead[T]`, `OpportunityFact`, `QualificationFact`, `MetricFact`, `HistoricalRead`, and source-reader functions.
- Must never call operational repository `initialize()` during report reads.

- [ ] **Step 1: Define RED tests around the no-side-effect boundary**

The test defines its own window explicitly:

```python
from datetime import datetime, timezone

from app.metrics.models import ReportWindow
from app.metrics.sources import read_outreach_facts

UTC = timezone.utc


def test_missing_optional_sqlite_source_is_not_created(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    window = ReportWindow(
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 8, 31, 23, 59, tzinfo=UTC),
    )
    result = read_outreach_facts(missing, window)
    assert result.coverage == "UNKNOWN"
    assert not missing.exists()
```

Add tests that Opportunity facts filter on persisted `discovered_at`; missing applications root stays absent; malformed `application_packet.json` is excluded with warning; valid typed PREPARED packet is included; native `DraftSnapshot` and `SendReceipt` deserialize from current Outreach schema; Relationship events map only `REPLIED`, `PROCESS_OPENED`, `PROCESS_CLOSED`; missing history DB remains absent.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_sources.py`

Expected: FAIL because `app.metrics.sources` does not exist.

- [ ] **Step 3: Implement exact source contracts**

Use these internal types:

```python
EvidenceClass = Literal["NATIVE", "IMPORTED_PROVIDER", "MANUAL"]
MetricFactKind = Literal[
    "PACKET_PREPARED", "DRAFT", "SEND", "REPLY", "PROCESS_OPENED", "PROCESS_CLOSED"
]

@dataclass(frozen=True)
class SourceRead(Generic[T]):
    items: tuple[T, ...]
    coverage: Coverage
    basis: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class OpportunityFact:
    opportunity_id: str
    discovered_at: datetime

@dataclass(frozen=True)
class QualificationFact:
    opportunity_id: str
    tier: Literal["HIGH", "MEDIUM", "STRETCH", "DISCARD"]
    observed_at: datetime
    scoring_version: str

@dataclass(frozen=True)
class MetricFact:
    fact_id: str
    kind: MetricFactKind
    opportunity_id: str | None
    account_id: str | None
    occurred_at: datetime
    evidence_class: EvidenceClass
    exact_anchor: str | None
    link_confidence: float
    draft_sha256: str | None = None
    thread_anchor: str | None = None
```

`MetricFact` remains internal and is never serialized as report output.

- [ ] **Step 4: Implement read-only SQLite connection helper**

```python
def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection
```

Check `path.exists()` first. Missing path returns `SourceRead(items=(), coverage="UNKNOWN", ...)` and never calls `mkdir`, `touch` or `initialize`.

- [ ] **Step 5: Implement native mappings against current schemas**

- Opportunity DB: select canonical `opportunities` columns and validate `Opportunity`; use `discovered_at`.
- Application packets: recursively read only `*/application_packet.json`; validate `ApplicationPacket`; require `status="PREPARED"`; fact time is `created_at`.
- Outreach drafts: `outreach_snapshots WHERE entity_type='draft_snapshot'`; validate `DraftSnapshot`; exact anchor `draft:{draft_sha256}`.
- Outreach sends: `send_receipts`; validate `SendReceipt`; exact anchor `gmail-message:{provider_message_id}`; preserve `draft_sha256`; `thread_anchor` is `gmail-thread:{provider_thread_id}` when present.
- Relationship events: `relationship_events` filtered to `REPLIED`, `PROCESS_OPENED`, `PROCESS_CLOSED`; validate `RelationshipEvent`; use non-empty `source_ref` as exact anchor when present, otherwise use the native event ID only as a native-identity anchor.
- Historical DB: validate `HistoricalObservation`; map `IMPORTED_GMAIL -> IMPORTED_PROVIDER`, `MANUAL_ASSERTION -> MANUAL`; derive exact anchors only from explicit provider/source IDs, never from company text/timestamp proximity.

- [ ] **Step 6: Implement optional Radar evidence reader without scoring calls**

Read explicitly configured serialized `RadarAssessment` JSON files. Validate current typed models. Use `enrichment.created_at` as recorded assessment time and the already-stored tier/version fields. Never import or call `rank_assessment`, `best_track_assessments`, extractor or current scoring code.

Without a complete historical Radar corpus declaration, known qualification facts remain PARTIAL; absence is UNKNOWN.

- [ ] **Step 7: Run GREEN**

```bash
pytest -q tests/test_metrics_sources.py tests/test_outreach_repository.py tests/test_relationship_repository.py tests/test_repository.py
```

Expected: PASS with no operational repository behavior change.

- [ ] **Step 8: Commit**

```bash
git add app/metrics/sources.py tests/test_metrics_sources.py
git commit -m "feat: add read-only search health sources"
```

---

### Task 4: Exact Reconciliation and Evidence Precedence

**Files:**
- Create: `app/metrics/projection.py`
- Create: `tests/test_metrics_reconciliation.py`

**Interfaces:**
- Consumes: normalized `MetricFact` values.
- Produces: `ReconciliationResult`, `reconcile_facts(native, historical)`.

- [ ] **Step 1: Write RED tests using explicit facts**

```python
from datetime import datetime, timezone

from app.metrics.projection import reconcile_facts
from app.metrics.sources import MetricFact

UTC = timezone.utc
NOW = datetime(2026, 8, 20, tzinfo=UTC)


def test_native_send_wins_over_exact_same_imported_provider_message():
    native = MetricFact(
        fact_id="native-send-1", kind="SEND", opportunity_id="opp-1", account_id=None,
        occurred_at=NOW, evidence_class="NATIVE", exact_anchor="gmail-message:m-1",
        link_confidence=1.0, draft_sha256="a" * 64, thread_anchor="gmail-thread:t-1",
    )
    imported = MetricFact(
        fact_id="hist-send-1", kind="SEND", opportunity_id="opp-1", account_id=None,
        occurred_at=NOW, evidence_class="IMPORTED_PROVIDER", exact_anchor="gmail-message:m-1",
        link_confidence=1.0, draft_sha256=None, thread_anchor="gmail-thread:t-1",
    )
    result = reconcile_facts((native,), (imported,))
    assert len(result.facts) == 1
    assert result.facts[0].evidence_class == "NATIVE"


def test_same_opportunity_without_exact_anchor_is_not_collapsed():
    native = MetricFact(
        fact_id="native-reply", kind="REPLY", opportunity_id="opp-1", account_id=None,
        occurred_at=NOW, evidence_class="NATIVE", exact_anchor=None,
        link_confidence=1.0,
    )
    imported = MetricFact(
        fact_id="hist-reply", kind="REPLY", opportunity_id="opp-1", account_id=None,
        occurred_at=NOW, evidence_class="IMPORTED_PROVIDER", exact_anchor=None,
        link_confidence=1.0,
    )
    result = reconcile_facts((native,), (imported,))
    assert len(result.facts) == 2
    assert result.has_ambiguity is True
```

Add manual-vs-provider precedence and different-message-ID non-collapse cases. Prove `link_confidence < 1.0` remains observable but is not linkage-eligible.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_reconciliation.py`

Expected: FAIL on missing reconciliation implementation.

- [ ] **Step 3: Implement exact-anchor reconciliation**

```python
_EVIDENCE_RANK = {"NATIVE": 3, "IMPORTED_PROVIDER": 2, "MANUAL": 1}
```

Only facts with the same non-null `exact_anchor` and same `kind` may collapse. Select highest evidence rank; deterministic same-rank tie-break is `(occurred_at, fact_id)`. Never derive anchors from company similarity, subject, same-day proximity or nearest timestamp.

When same-kind facts claim the same explicit opportunity link but exact reconciliation is unavailable, keep both, mark ambiguity and exclude the lower-certainty ambiguous imported fact from linkage-dependent ratios.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_metrics_reconciliation.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/metrics/projection.py tests/test_metrics_reconciliation.py
git commit -m "feat: reconcile search history by exact evidence"
```

---

### Task 5: Search Health Projection and Coverage

**Files:**
- Modify: `app/metrics/projection.py`
- Create: `tests/test_metrics_projection.py`

**Interfaces:**
- Consumes: `MetricsInput` composed from typed `SourceRead` results.
- Produces: `project_search_health(inputs, window, generated_at) -> SearchHealthReport`.

- [ ] **Step 1: Add the exact projection input container**

In `app/metrics/projection.py`:

```python
@dataclass(frozen=True)
class MetricsInput:
    opportunities: SourceRead[OpportunityFact]
    qualifications: SourceRead[QualificationFact]
    packets: SourceRead[MetricFact]
    outreach: SourceRead[MetricFact]
    relationships: SourceRead[MetricFact]
    history: SourceRead[MetricFact]
    history_batches: tuple[HistoricalImportBatch, ...] = ()
```

- [ ] **Step 2: Write RED count tests**

Build `MetricsInput` directly with fictional `SourceRead` instances. Assert:

- one persisted opportunity produces `opportunities_observed=1` and `opportunities_new=1`;
- no Radar history produces `qualified_high.value is None` and `coverage="UNKNOWN"`;
- partial known HIGH/MEDIUM assessments can emit lower-bound numeric counts with `PARTIAL` coverage;
- only typed PREPARED packet facts count;
- exact native/imported duplicate send counts once;
- unmatched historical reply may contribute to a PARTIAL observed-reply count but not a linkage ratio.

- [ ] **Step 3: Write RED ratio-cohort test with explicit facts**

Construct two native sends with exact thread anchors, one exact linked reply, and a historical import batch whose declared scope covers those threads. Assert `send_to_reply_rate` has numerator `1`, denominator `2`, value `0.5`. Add a second test where the batch is `SELECTED_THREADS`/incomplete and assert `value is None` or a PARTIAL ratio only when the covered cohort itself can be exactly identified.

- [ ] **Step 4: Run RED**

Run: `pytest -q tests/test_metrics_projection.py`

Expected: FAIL because full projection does not exist.

- [ ] **Step 5: Implement deterministic count projection**

Counts come from reconciled facts. A count may be numeric with `PARTIAL` coverage when it means "at least this many observed". Use `None` when even that numeric interpretation is not defensible.

For qualification, deduplicate known assessments by `opportunity_id`. If more than one historical qualifying assessment exists, use deterministic strongest tier order `HIGH > MEDIUM`; never recompute tier. If stored scoring versions differ, retain a warning.

- [ ] **Step 6: Implement conversion cohorts from compatible linkage, not headline division**

- `qualification_rate`: known qualifying observed opportunity IDs / observed opportunity IDs only when historical qualification coverage supports the full denominator; otherwise null.
- `draft_to_send_rate`: confirmed sends linked by `draft_sha256` to verified drafts / verified drafts inside a defensible send-observation cohort.
- `send_to_reply_rate`: reconciled replies linked by exact thread/source identity or exact opportunity lineage / confirmed sends inside the declared reply-observation cohort.
- `reply_to_process_rate`: process-open facts linked to replies by exact opportunity/account lineage / replies inside a defensible process-observation cohort.

Imported evidence requires `link_confidence == 1.0` to enter linkage-dependent numerators. Lower-confidence observations remain counts/warnings only.

- [ ] **Step 7: Implement top-level coverage propagation**

`CoverageSummary` reports `radar`, `outreach`, `replies`, `processes`. Never upgrade to COMPLETE merely because a number exists. COMPLETE requires declared complete evidence scope for the relevant window/cohort; PARTIAL means useful but incomplete evidence; UNKNOWN means no defensible metric population.

- [ ] **Step 8: Run GREEN**

```bash
pytest -q tests/test_metrics_projection.py tests/test_metrics_reconciliation.py tests/test_metrics_models.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/metrics/projection.py tests/test_metrics_projection.py
git commit -m "feat: project provenance-aware search health metrics"
```

---

### Task 6: Search Health CLI and Aggregate JSON

**Files:**
- Create: `app/metrics/report.py`
- Create: `tests/test_metrics_report_cli.py`

**Interfaces:**
- Consumes: report boundaries and source paths.
- Produces: compact human stdout and aggregate JSON at `artifacts/metrics/search-health.json` by default.

- [ ] **Step 1: Write RED CLI tests**

Test direct `main(argv)` behavior for:

- `--from 2026-08-01 --as-of 2026-08-31T23:00:00+00:00`;
- reverse window exits non-zero;
- conflicting `--to` plus `--as-of` exits non-zero;
- missing optional DBs remain nonexistent;
- aggregate JSON does not contain fictional private provider IDs/names used in source fixtures;
- repeated execution with identical sources and fixed `--as-of` is byte-identical;
- human output says `unknown`/`partial coverage` instead of rendering absent evidence as `0`.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_report_cli.py`

Expected: FAIL because report CLI does not exist.

- [ ] **Step 3: Implement exact CLI arguments**

```text
--from YYYY-MM-DD|ISO_DATETIME          required
--to YYYY-MM-DD|ISO_DATETIME            optional
--as-of YYYY-MM-DD|ISO_DATETIME         optional; defaults to current UTC
--opportunity-db opportunities.db
--relationships-db state/relationships.local.sqlite3
--outreach-db state/outreach.local.sqlite3
--history-db state/history.local.sqlite3
--applications-root artifacts/applications
--radar-root artifacts/radar
--output artifacts/metrics/search-health.json
```

Reject simultaneous `--to` and `--as-of`. Date-only start becomes `00:00:00Z`; date-only end/as-of becomes `23:59:59.999999Z`. Set `generated_at` equal to the resolved as-of/end boundary in V1 so fixed inputs yield fully reproducible JSON.

- [ ] **Step 4: Implement source orchestration and human rendering**

Call only Task 3 read functions, construct `MetricsInput`, call `project_search_health`, then render sections `DISCOVERY`, `EXECUTION`, `OUTCOMES`, `CONVERSION`, `COVERAGE`. Do not print company/contact/provider identifiers.

- [ ] **Step 5: Implement deterministic JSON write**

```python
payload = report.model_dump(mode="json")
text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
```

Create output parent only after all reads/projection succeed. Source paths are never created by reading.

- [ ] **Step 6: Run GREEN**

```bash
pytest -q tests/test_metrics_report_cli.py tests/test_metrics_projection.py tests/test_metrics_sources.py
python -m compileall -q app/metrics
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/metrics/report.py tests/test_metrics_report_cli.py
git commit -m "feat: add search health CLI report"
```

---

### Task 7: Private August Dogfood Backfill and Evidence Review

**Files:**
- No real user data is committed.
- Private input: `state/history-import-2026-08.local.json`.
- Private DB: `state/history.local.sqlite3`.
- Private output: `artifacts/metrics/search-health.json` and `artifacts/metrics/search-health.asof.local.txt`.

**Interfaces:**
- Consumes: explicitly authorized Gmail evidence for `2026-08-01` through the captured acceptance time plus existing local Opportunity OS state.
- Produces: one private import batch and one private Search Health report used as acceptance evidence.

- [ ] **Step 1: Build the normalized private manifest outside Git**

Select only job-search outreach messages/threads inside the August window. Save only fields accepted by `HistoricalImportManifest`. Do not persist body, snippet, raw MIME, attachment payload, subject text, arbitrary provider payload, tokens or credentials.

Provider-confirmed event: `event_confidence=1.0`. Exact opportunity/account linkage: `link_confidence=1.0`. If linkage is uncertain, keep the opportunity/account null or use a lower `link_confidence`; never guess.

- [ ] **Step 2: Declare honest batch coverage**

Use `selection_scope="SELECTED_THREADS"` unless the complete declared outreach-thread population was actually reviewed. Only a complete reviewed population may use `ALL_DECLARED_OUTREACH_THREADS` with `complete_for_declared_scope=true`.

- [ ] **Step 3: Import twice and verify idempotence**

```bash
python -m app.metrics.import_history \
  --manifest state/history-import-2026-08.local.json \
  --history-db state/history.local.sqlite3

python -m app.metrics.import_history \
  --manifest state/history-import-2026-08.local.json \
  --history-db state/history.local.sqlite3
```

Expected: same batch identity; second run creates no duplicate observation.

- [ ] **Step 4: Capture one exact as-of timestamp and generate the report**

```bash
mkdir -p artifacts/metrics
AS_OF="$(python -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())')"
printf '%s\n' "$AS_OF" > artifacts/metrics/search-health.asof.local.txt
python -m app.metrics.report \
  --from 2026-08-01 \
  --as-of "$AS_OF" \
  --output artifacts/metrics/search-health.json
```

Both output files are private/ignored.

- [ ] **Step 5: Review report against actual Gmail/native evidence**

Verify draft/send counts against private state; inspect any exact native/imported reconciliation present; inspect at least one unmatched/partial observation if one exists; verify missing Radar history remains partial/unknown rather than being recomputed; verify aggregate JSON contains no private identifiers.

If a discrepancy appears, first encode it as a RED regression in the relevant metrics test before changing implementation.

- [ ] **Step 6: Re-run with the same captured timestamp**

```bash
AS_OF="$(cat artifacts/metrics/search-health.asof.local.txt)"
cp artifacts/metrics/search-health.json artifacts/metrics/search-health.first.local.json
python -m app.metrics.report \
  --from 2026-08-01 \
  --as-of "$AS_OF" \
  --output artifacts/metrics/search-health.json
cmp artifacts/metrics/search-health.first.local.json artifacts/metrics/search-health.json
```

Expected: `cmp` exits 0.

- [ ] **Step 7: Record only redacted acceptance evidence**

Public PR notes may state pass/fail, coverage classes, test totals and that real dogfooding succeeded. Do not paste personal counts tied to identifiable companies/contacts, provider IDs, message content or the private report.

---

### Task 8: Product Documentation and Release Contract

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Create: `tests/test_metrics_release_contract.py`

**Interfaces:**
- Consumes: successful Task 7 acceptance.
- Produces: accurate public Search Health product contract without personal metrics.

- [ ] **Step 1: Write RED release-contract test**

The test reads public docs and requires these concepts:

```text
Search Health
COMPLETE / PARTIAL / UNKNOWN
native history != reconstructed history
missing evidence is not zero
metrics do not grant send/apply/follow-up authority
```

Do not assert any real operator count.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_release_contract.py`

Expected: FAIL until docs describe the implemented slice.

- [ ] **Step 3: Update README**

Add Search Health as local evidence-aware reporting. Document canonical report/import commands, aggregate-only JSON, historical-vs-native provenance, coverage semantics and the no-authority boundary. Do not market it as a success predictor, productivity score, causal optimizer or automatic follow-up engine.

- [ ] **Step 4: Update ROADMAP**

Move pipeline reporting from future work into the implemented slice. Keep source/language/strategy comparisons, dashboard UI, median timing and actionable-next-state summaries deferred.

- [ ] **Step 5: Run GREEN**

Run: `pytest -q tests/test_metrics_release_contract.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md ROADMAP.md tests/test_metrics_release_contract.py
git commit -m "docs: document search health reporting"
```

---

### Task 9: Full Verification, PR and Merge Gate

**Files:** no new behavior unless verification exposes a regression, in which case add a failing test first.

**Interfaces:** implementation branch -> `main`.

- [ ] **Step 1: Run full local verification**

```bash
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check main...HEAD
```

Expected: full suite PASS, compile PASS, whitespace clean.

- [ ] **Step 2: Run explicit private-file check**

```bash
git ls-files -- \
  'state/history.local.sqlite3*' \
  'state/history-import*.local.json' \
  'artifacts/metrics/**'
```

Expected: no output.

Inspect `git diff --stat main...HEAD` and verify no unrelated scoring, send-gate, Gmail mutation, API-route or CV-authority files changed.

- [ ] **Step 3: Open PR**

Title:

```text
feat: add provenance-aware search health reporting
```

PR body must state: read-only metrics boundary; separate historical store; native precedence; exact-only reconciliation; coverage semantics; no mailbox-wide sync; no new runtime dependency; private August dogfood performed without publishing PII; exact RED/GREEN/full-suite evidence.

- [ ] **Step 4: Require existing CI on exact PR head**

Require pytest, compile, whitespace, private-file guard, recruiter previews, offline-runtime build Python 3.12/3.13, and offline-runtime verification Python 3.12/3.13 to succeed. Search Health must not weaken the recruiter runtime acceptance path.

- [ ] **Step 5: Resolve review findings with TDD**

No merge with unresolved correctness/privacy feedback. Every behavioral correction begins with a failing regression, then minimal fix, focused GREEN, full verification.

- [ ] **Step 6: Merge only the verified head**

Use the exact reviewed PR head SHA as merge expectation. After merge, inspect `main` and post-merge workflow state before calling the feature complete.

---

## Plan Self-Review

- **Spec coverage:** typed metrics, separate history, explicit import batch coverage, read-only sources, exact reconciliation, evidence precedence, all approved V1 counts/ratios, CLI+JSON, private August dogfood, privacy guards, docs and CI each map to a task.
- **No placeholders:** execution-time acceptance timestamp is captured by a concrete command; tests use explicit constructors/data rather than undefined helper names.
- **Type consistency:** `Coverage` and report contracts are defined in Task 1; historical types in Task 2; `SourceRead`/facts in Task 3; reconciliation in Task 4; `MetricsInput`/projection in Task 5; CLI consumes those exact interfaces in Task 6.
- **Scope check:** no UI, API metrics route, multi-user work, strategy winner, causal claim, auto-follow-up/send, mailbox sync or historical rescoring was added.
- **Privacy:** ignore rules and CI guard land before private dogfood; aggregate output never serializes `MetricFact` anchors.
- **Determinism:** exact anchors, deterministic precedence, fixed as-of and sorted JSON are explicit.
- **TDD:** every behavior task begins RED, runs the failure, adds minimal behavior, runs GREEN, then commits.
