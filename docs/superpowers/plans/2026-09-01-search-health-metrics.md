# Opportunity OS Search Health Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, provenance-aware Search Health report that combines native Opportunity OS state with explicitly imported historical observations without turning missing history into false zeroes.

**Architecture:** Introduce a focused `app.metrics` package. Read native Opportunity, ApplicationPacket, Outreach and Relationship state without creating missing databases; keep reconstructed history in a separate private SQLite store; normalize both into metric facts; reconcile only on exact anchors with native evidence taking precedence; project counts, conversion cohorts and `COMPLETE/PARTIAL/UNKNOWN` coverage into a schema-versioned CLI/JSON report.

**Tech Stack:** Python 3.12+, Pydantic v2, SQLite/stdlib `sqlite3`, argparse, pytest. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-08-31-search-health-metrics-design.md`

## Global Constraints

- Initial dogfood reporting window is `2026-08-01` through the requested report as-of time.
- `native ledger != historical reconstruction`; historical backfill never fabricates `OutreachEvent`, `SendReceipt` or `RelationshipEvent` rows.
- Exact evidence precedence is `native confirmed fact > imported provider evidence > manual historical assertion > unknown`.
- `UNKNOWN` is never silently converted to zero.
- Metrics are read-only over operational state: no apply, approval, send, relationship mutation, Gmail import into Relationship Memory, or opportunity-status mutation.
- Historical HIGH/MEDIUM qualification is never recomputed with the current scoring implementation and presented as historical truth.
- V1 output is CLI + aggregate JSON only: no FastAPI metrics endpoint, web dashboard, multi-user analytics, productivity score or causal strategy ranking.
- Historical Gmail evidence is selected/authorized input; no mailbox-wide synchronization is introduced.
- Private history may contain exact reconciliation identifiers locally, but aggregate JSON must contain no provider message/thread IDs, contact names, addresses, subjects, bodies, company-specific private notes or credentials.
- Historical event certainty and linkage certainty remain separate as `event_confidence` and `link_confidence` in `[0, 1]`.
- No fuzzy company-name, subject-similarity or nearest-timestamp matching is allowed for deduplication.
- Missing optional source paths do not create databases or directories as a side effect; they degrade coverage and emit bounded warnings.
- `opportunities_observed` and `opportunities_new` intentionally have the same value in V1 because the current opportunity repository persists one canonical first observation and does not persist gross duplicate observations.
- Fixed source state + fixed report window + fixed `--as-of` must produce deterministic metric values and stable JSON ordering.
- Real August history, real Gmail evidence and the operator's generated Search Health JSON remain private/untracked.

---

## File Map

### New production files

- `app/metrics/__init__.py` — package exports only; no side effects.
- `app/metrics/models.py` — report window, coverage, count/ratio, source-summary and Search Health contracts.
- `app/metrics/history.py` — strict historical-observation/import models plus the private SQLite history repository.
- `app/metrics/sources.py` — read-only adapters over Opportunity DB, ApplicationPacket files, Outreach DB, Relationship DB, optional Radar evidence and historical DB.
- `app/metrics/projection.py` — normalized facts, exact reconciliation, coverage propagation and Search Health projection.
- `app/metrics/import_history.py` — explicit private manifest -> historical SQLite CLI; this is the only V1 history write entrypoint.
- `app/metrics/report.py` — Search Health CLI, human rendering and aggregate JSON output.

### New tests

- `tests/test_metrics_models.py`
- `tests/test_metrics_history.py`
- `tests/test_metrics_sources.py`
- `tests/test_metrics_reconciliation.py`
- `tests/test_metrics_projection.py`
- `tests/test_metrics_report_cli.py`
- `tests/test_metrics_release_contract.py`

### Existing files modified only where the slice requires it

- `.gitignore` — ignore `artifacts/metrics/` and private history-import manifests.
- `.github/workflows/tests.yml` — strengthen private/generated-file guard for Search Health local artifacts.
- `README.md` — document Search Health only after the dogfood run proves the path.
- `ROADMAP.md` — mark reporting slice implemented only after acceptance evidence exists.

Do not modify `app/main.py`, FastAPI routes, Radar scoring, CV semantic authority, Outreach send gates, Relationship projection rules, Gmail read behavior or existing operational repository write semantics for this slice.

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

Create `tests/test_metrics_models.py` with focused contract tests:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.metrics.models import CountMetric, RatioMetric, ReportWindow, SearchHealthReport

UTC = timezone.utc


def test_report_window_rejects_reverse_range():
    with pytest.raises(ValidationError):
        ReportWindow(
            start=datetime(2026, 8, 2, tzinfo=UTC),
            end=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_unknown_ratio_keeps_denominator_without_fabricating_zero():
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

Also test timezone awareness, ratio value bounds `[0, 1]`, non-negative counts, exact `report_version="search-health-v1"`, and deterministic JSON field ordering from the typed model.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_models.py`

Expected: FAIL because `app.metrics.models` does not exist.

- [ ] **Step 3: Implement minimal strict Pydantic contracts**

Use `ConfigDict(extra="forbid")` and literal coverage values:

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

`SearchHealthCounts` has exactly the ten V1 count fields from the spec; `SearchHealthRatios` has exactly the four approved ratios. `SearchHealthReport` contains `report_version`, `generated_at`, `window`, `counts`, `ratios`, `coverage`, `warnings`, and `source_summary`.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_metrics_models.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/metrics/__init__.py app/metrics/models.py tests/test_metrics_models.py
git commit -m "feat: add search health report contracts"
```

---

### Task 2: Private Historical Observation Store and Strict Import Contract

**Files:**
- Create: `app/metrics/history.py`
- Create: `app/metrics/import_history.py`
- Create: `tests/test_metrics_history.py`
- Modify: `.gitignore`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: an explicit private JSON `HistoricalImportManifest` containing normalized evidence only.
- Produces: `HistoricalObservation`, `HistoricalImportBatch`, `HistoricalImportManifest`, `SQLiteHistoricalRepository`, `import_manifest(...)` and CLI `python -m app.metrics.import_history`.
- Persists only: `state/history.local.sqlite3` by default.

- [ ] **Step 1: Write RED tests for strict history models and idempotence**

Tests must cover:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.metrics.history import HistoricalObservation

UTC = timezone.utc


def test_provider_reply_can_be_certain_while_link_is_unknown():
    observation = HistoricalObservation(
        observation_id="hist-reply-1",
        kind="REPLY_OBSERVED",
        opportunity_id=None,
        account_id=None,
        company="Example Labs",
        role=None,
        occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
        observed_at=datetime(2026, 8, 31, tzinfo=UTC),
        provenance="IMPORTED_GMAIL",
        source_ref="gmail-message-1",
        provider_message_id="m-1",
        provider_thread_id="t-1",
        event_confidence=1.0,
        link_confidence=0.0,
        reconstruction_note="provider-confirmed reply; opportunity unmatched",
    )
    assert observation.event_confidence == 1.0
    assert observation.link_confidence == 0.0


def test_history_model_rejects_raw_body_field():
    with pytest.raises(ValidationError):
        HistoricalObservation.model_validate({
            # valid required fields omitted here only after a valid base fixture is built
            **valid_history_payload(),
            "body": "private mail body",
        })
```

Add repository tests proving: identical import is idempotent; same `observation_id` with different semantic payload fails closed; batch IDs are idempotent/conflict-safe; a missing history DB is not created by a read-only `list_*` call; `initialize()` is called only by the explicit import path.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_history.py`

Expected: FAIL on missing history types/repository/importer.

- [ ] **Step 3: Implement strict history models**

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

`HistoricalObservation` includes the approved fields `event_confidence`, `link_confidence` and bounded `reconstruction_note`. Do not add `body`, `snippet`, `subject`, raw MIME, attachment payload, arbitrary metadata, auth token or credentials fields.

- [ ] **Step 4: Implement private SQLite schema and fail-closed idempotence**

Use two tables:

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

On an existing primary key, deserialize the stored typed model. Return it only when semantic equality is exact; otherwise raise `ValueError("historical observation_id conflict")` or the batch equivalent.

- [ ] **Step 5: Implement explicit manifest import CLI**

Command:

```bash
python -m app.metrics.import_history \
  --manifest state/history-import-2026-08.local.json \
  --history-db state/history.local.sqlite3
```

The CLI validates the entire manifest before initializing/writing the DB. Output only bounded counts and batch ID; never echo private observations/provider IDs.

- [ ] **Step 6: Strengthen privacy ignore/CI guard**

Add to `.gitignore`:

```text
artifacts/metrics/
state/history.local.sqlite3
state/history.local.sqlite3-*
state/history-import*.local.json
```

Add the same Search Health paths to the existing `git ls-files` forbidden set in `.github/workflows/tests.yml`.

- [ ] **Step 7: Run GREEN and privacy regression**

Run:

```bash
pytest -q tests/test_metrics_history.py
git diff --check
```

Expected: PASS; no private files tracked.

- [ ] **Step 8: Commit**

```bash
git add app/metrics/history.py app/metrics/import_history.py tests/test_metrics_history.py .gitignore .github/workflows/tests.yml
git commit -m "feat: add private historical observation store"
```

---

### Task 3: Read-Only Native and Artifact Sources

**Files:**
- Create: `app/metrics/sources.py`
- Create: `tests/test_metrics_sources.py`

**Interfaces:**
- Consumes: `ReportWindow`; paths to opportunity DB, outreach DB, relationship DB, history DB, applications root and optional Radar evidence root.
- Produces: `SourceRead[T]`, `OpportunityFact`, `QualificationFact`, `MetricFact`, and read functions used by Task 5.
- Must never call existing repository `initialize()` methods during report reads.

- [ ] **Step 1: Write RED tests for missing-source safety**

Start with the side-effect boundary:

```python
def test_missing_optional_sqlite_source_is_not_created(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    result = read_outreach_facts(missing, window())
    assert result.coverage == "UNKNOWN"
    assert not missing.exists()
```

Also test that Opportunity facts are filtered by `discovered_at`; missing application root returns UNKNOWN without creating it; malformed `application_packet.json` is excluded with a warning; valid `PREPARED` packet counts; native send receipts and draft snapshots deserialize through current `DraftSnapshot`/`SendReceipt` models; relationship `REPLIED`, `PROCESS_OPENED`, `PROCESS_CLOSED` events are read in-window; historical observations are read without initializing a missing history DB.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_sources.py`

Expected: FAIL because `app.metrics.sources` does not exist.

- [ ] **Step 3: Implement a read-only SQLite connection helper**

Use SQLite URI read-only mode after checking path existence:

```python
def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
```

A missing path returns a `SourceRead(items=[], coverage="UNKNOWN", warnings=[...])`; do not call `mkdir`, `touch` or `initialize`.

- [ ] **Step 4: Implement exact source mappings**

Use current persisted schemas:

- Opportunity: query `opportunities.payload` does not exist; select the canonical columns from `opportunities` and validate with `Opportunity`, using `discovered_at` as the observation time.
- Outreach drafts: query `outreach_snapshots WHERE entity_type='draft_snapshot'`, validate `payload_json` as `DraftSnapshot`.
- Outreach sends: query `send_receipts`, validate `payload_json` as `SendReceipt`.
- Relationships: query `relationship_events WHERE kind IN ('REPLIED','PROCESS_OPENED','PROCESS_CLOSED')`, validate `payload_json` as `RelationshipEvent`.
- Prepared packets: recursively read only `*/application_packet.json`, validate `ApplicationPacket`, require `status='PREPARED'`, filter by `created_at`.
- Historical DB: query typed `historical_observations` only when the DB exists.

`MetricFact` carries only fields needed for reconciliation: stable fact ID, kind, opportunity/account link if known, occurred time, evidence class, exact provider/entity anchors when available, and linkage confidence. Private anchors never leave projection internals.

- [ ] **Step 5: Add optional historical Radar evidence reader without recomputation**

Accept serialized canonical `RadarAssessment` JSON files from an explicitly configured private root. Validate the current typed model and read the already-recorded tier/versions. Never call `rank_assessment`, `best_track_assessments`, the extractor or current scoring code from metrics.

If Radar artifacts are absent, qualification coverage is `UNKNOWN`. If some valid assessments exist without a complete declared historical corpus, qualified counts may be `PARTIAL`; the reader must not claim full qualification coverage merely because one batch file exists.

- [ ] **Step 6: Run GREEN**

Run: `pytest -q tests/test_metrics_sources.py tests/test_outreach_repository.py tests/test_relationship_repository.py tests/test_repository.py`

Expected: PASS with no existing repository behavior changes.

- [ ] **Step 7: Commit**

```bash
git add app/metrics/sources.py tests/test_metrics_sources.py
git commit -m "feat: add read-only search health sources"
```

---

### Task 4: Exact Reconciliation and Evidence Precedence

**Files:**
- Create: `tests/test_metrics_reconciliation.py`
- Create/Modify: `app/metrics/projection.py` (reconciliation primitives first)

**Interfaces:**
- Consumes: normalized `MetricFact` lists from native and historical sources.
- Produces: `ReconciliationResult`, `reconcile_facts(native, historical)` and reconciled facts with private exact anchors removed from public serialization.

- [ ] **Step 1: Write RED reconciliation tests**

Cover the exact rules:

```python
def test_native_send_wins_over_same_imported_provider_message():
    result = reconcile_facts(
        native=[native_send(provider_message_id="m-1")],
        historical=[gmail_send(provider_message_id="m-1")],
    )
    assert len(result.facts) == 1
    assert result.facts[0].evidence_class == "NATIVE"


def test_manual_assertion_loses_to_exact_imported_provider_fact():
    result = reconcile_facts(
        native=[],
        historical=[
            manual_send(exact_anchor="send:m-1"),
            gmail_send(provider_message_id="m-1"),
        ],
    )
    assert len(result.facts) == 1
    assert result.facts[0].evidence_class == "IMPORTED_PROVIDER"


def test_no_exact_anchor_means_no_fuzzy_collapse():
    result = reconcile_facts(
        native=[native_reply(opportunity_id="opp-1", exact_anchor=None)],
        historical=[gmail_reply(opportunity_id="opp-1", exact_anchor=None)],
    )
    assert len(result.facts) == 2
    assert result.has_ambiguity
```

Also prove different provider message IDs are not collapsed even when company/opportunity/timestamp are similar; imported observation with `link_confidence < 1.0` remains observable but is marked ineligible for linkage-dependent ratios.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_reconciliation.py`

Expected: FAIL on missing reconciliation functions.

- [ ] **Step 3: Implement exact-anchor grouping and rank precedence**

Use an internal evidence rank:

```python
_EVIDENCE_RANK = {
    "NATIVE": 3,
    "IMPORTED_PROVIDER": 2,
    "MANUAL": 1,
}
```

Only group facts when they share a non-null exact anchor and event kind. Select the highest-ranked evidence; deterministic tie-break is `(evidence rank desc, occurred_at asc, fact_id asc)`. Never use company string similarity, subject text, day proximity or nearest timestamps to create an anchor.

When native and imported facts share event kind + explicit opportunity link but no exact common anchor, preserve both and emit an ambiguity warning; do not silently discard either.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_metrics_reconciliation.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/metrics/projection.py tests/test_metrics_reconciliation.py
git commit -m "feat: reconcile search history by exact evidence"
```

---

### Task 5: Search Health Projection, Counts, Conversion Cohorts and Coverage

**Files:**
- Modify: `app/metrics/projection.py`
- Create: `tests/test_metrics_projection.py`

**Interfaces:**
- Consumes: `ReportWindow` plus `SourceRead` values from Task 3 and reconciliation from Task 4.
- Produces: `project_search_health(...) -> SearchHealthReport`.

- [ ] **Step 1: Write RED tests for count semantics**

Create fictional source bundles proving:

- canonical opportunities are counted once in-window;
- `opportunities_new == opportunities_observed` in V1;
- known HIGH/MEDIUM assessments produce partial counts when historical Radar coverage is incomplete;
- no historical Radar evidence yields `value=None`/`UNKNOWN`, not zero;
- only valid `PREPARED` packets count;
- exact native/imported duplicate send counts once;
- unmatched historical reply can increase an observed PARTIAL reply count but cannot enter a linkage-dependent ratio;
- missing reply/process coverage produces PARTIAL/UNKNOWN rather than 0%.

- [ ] **Step 2: Write RED tests for ratio cohorts**

Cover all four approved ratios and zero-denominator behavior:

```python
def test_send_to_reply_uses_only_defensibly_covered_linked_cohort():
    report = project_search_health(source_bundle_with(
        confirmed_sends=3,
        covered_sends=2,
        linked_replies=1,
    ))
    metric = report.ratios.send_to_reply_rate
    assert metric.numerator == 1
    assert metric.denominator == 2
    assert metric.value == 0.5
    assert metric.coverage == "PARTIAL"


def test_uncovered_send_cohort_does_not_publish_false_zero_rate():
    metric = project_search_health(source_bundle_with_uncovered_sends()).ratios.send_to_reply_rate
    assert metric.value is None
    assert metric.coverage in {"PARTIAL", "UNKNOWN"}
```

- [ ] **Step 3: Run RED**

Run: `pytest -q tests/test_metrics_projection.py`

Expected: FAIL because full projection does not exist.

- [ ] **Step 4: Implement deterministic count projection**

Compute counts from reconciled facts. Count metrics can carry a numeric lower bound with `PARTIAL` coverage; use `None` when no defensible numeric interpretation exists.

For qualification counts, deduplicate known assessments by `opportunity_id`; if the same opportunity has more than one historical qualifying assessment in-window, use deterministic strongest tier ordering `HIGH > MEDIUM` and preserve a warning when versions differ. Do not recompute the tier.

- [ ] **Step 5: Implement conversion cohort builders**

Build each ratio from linked compatible facts rather than dividing headline count fields:

- `qualification_rate`: qualifying observed opportunity IDs / observed opportunity IDs only when historical qualification coverage supports the denominator; otherwise `value=None`.
- `draft_to_send_rate`: confirmed sends that link to verified native drafts / verified drafts whose send observation scope is defensible.
- `send_to_reply_rate`: reconciled replies with defensible linkage / confirmed sends inside the declared reply-observation cohort.
- `reply_to_process_rate`: linked process-open facts / replies inside a defensible process-observation cohort.

Require `link_confidence == 1.0` for imported evidence to participate in a linkage-dependent numerator. Lower-confidence evidence remains visible through counts/warnings only.

- [ ] **Step 6: Implement coverage propagation**

Coverage is never upgraded merely because a numeric value exists. `COMPLETE` requires full declared source scope for the metric window/cohort; `PARTIAL` preserves observed lower-bound numbers; `UNKNOWN` means the projection cannot defend a numeric result.

The top-level `CoverageSummary` reports `radar`, `outreach`, `replies`, and `processes` using the weakest relevant source/cohort coverage needed for each domain.

- [ ] **Step 7: Run GREEN**

Run:

```bash
pytest -q tests/test_metrics_projection.py tests/test_metrics_reconciliation.py tests/test_metrics_models.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

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
- Consumes: source paths and report window CLI args.
- Produces: human stdout and schema-versioned aggregate JSON; default output `artifacts/metrics/search-health.json`.

- [ ] **Step 1: Write RED CLI tests**

Use subprocess/module invocation or direct `main(argv)` tests to cover:

- `--from 2026-08-01` with fixed `--as-of`;
- invalid reverse window exits non-zero;
- explicit missing optional DBs do not get created;
- default/explicit JSON output contains no private identifiers;
- fixed inputs + fixed `--as-of` produce byte-stable JSON except where the spec explicitly permits generated-time variation; set `generated_at=as_of` in V1 to make the artifact fully reproducible;
- human output prints `unknown` and `[partial coverage]` rather than `0` for missing evidence.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_report_cli.py`

Expected: FAIL because the report CLI does not exist.

- [ ] **Step 3: Implement CLI arguments**

Support:

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

Reject simultaneous conflicting `--to` and `--as-of`. Normalize date-only start to `00:00:00Z`; normalize a date-only end/as-of to `23:59:59.999999Z` for that date. Store the resolved aware timestamps in `ReportWindow`.

- [ ] **Step 4: Implement human renderer and JSON writer**

Human output follows the approved compact sections `DISCOVERY`, `EXECUTION`, `OUTCOMES`, `CONVERSION`, `COVERAGE`. Never print company/contact/provider details.

Write JSON using:

```python
payload = report.model_dump(mode="json")
json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
```

Create only the requested output parent after successful source reading/projection. A report read must not create source DBs.

- [ ] **Step 5: Add explicit public-output privacy assertion**

In tests, serialize a report built from private-looking fictional provider IDs/names and assert the aggregate JSON lacks strings such as the provider message ID, thread ID, contact email, subject and reconstruction note.

- [ ] **Step 6: Run GREEN**

Run:

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
- Private runtime inputs: `state/history-import-2026-08.local.json`, `state/history.local.sqlite3`.
- Private output: `artifacts/metrics/search-health.json`.

**Interfaces:**
- Consumes: explicitly authorized Gmail evidence for `2026-08-01` through the fixed dogfood as-of time plus existing local Opportunity OS state.
- Produces: a private imported history batch and one private Search Health report used as acceptance evidence.

- [ ] **Step 1: Build the private normalized manifest outside Git**

Select only job-search outreach threads/messages inside the August window. Materialize normalized observations with the strict fields accepted by `HistoricalImportManifest`; do not save bodies, raw MIME, attachments, arbitrary provider payloads, tokens or credentials.

For each provider-confirmed event, set `event_confidence=1.0`. Set `link_confidence=1.0` only when the Opportunity/account link is exact; otherwise preserve `opportunity_id=None` or lower linkage confidence rather than guessing.

- [ ] **Step 2: Declare honest import coverage**

Use `selection_scope="SELECTED_THREADS"` unless the operator actually reviewed the complete declared outreach-thread population for the window. Only then use `ALL_DECLARED_OUTREACH_THREADS` with `complete_for_declared_scope=true`.

- [ ] **Step 3: Import twice to prove idempotence**

Run:

```bash
python -m app.metrics.import_history \
  --manifest state/history-import-2026-08.local.json \
  --history-db state/history.local.sqlite3
```

Run the exact command again. Expected: same bounded counts/batch identity; no duplicate observations.

- [ ] **Step 4: Generate a fixed-as-of Search Health report**

Run with a fixed reviewed timestamp, for example the actual acceptance timestamp captured at execution time:

```bash
python -m app.metrics.report \
  --from 2026-08-01 \
  --as-of <FIXED_ACCEPTANCE_ISO_TIMESTAMP> \
  --output artifacts/metrics/search-health.json
```

Before execution, replace `<FIXED_ACCEPTANCE_ISO_TIMESTAMP>` with the exact timezone-aware acceptance timestamp and record that value in the PR evidence; do not commit the private JSON.

- [ ] **Step 5: Manually reconcile the report against known Gmail/native evidence**

Check at least: one native/imported duplicate when available; one unmatched/partial observation when available; draft/send counts against actual private state; that missing Radar history remains partial/unknown rather than being recomputed; and that no private identifiers appear in the aggregate output.

If the report disagrees with source evidence, add a RED regression before changing projection logic.

- [ ] **Step 6: Re-run report with identical inputs**

Expected: byte-identical `artifacts/metrics/search-health.json` for fixed `--as-of` and unchanged source state.

- [ ] **Step 7: Record only redacted acceptance evidence**

PR notes may record pass/fail, coverage classes, test counts and whether real dogfooding succeeded. Do not paste personal company/contact/provider identifiers or the private report itself into the public PR.

---

### Task 8: Product Documentation and Release Contract After Dogfood Success

**Files:**
- Modify: `README.md`
- Modify: `ROADMAP.md`
- Create: `tests/test_metrics_release_contract.py`

**Interfaces:**
- Consumes: successful Task 7 dogfood evidence.
- Produces: public product description that accurately states Search Health boundaries without personal metrics.

- [ ] **Step 1: Write RED release-contract test**

Require public docs to preserve these statements/concepts:

```text
Search Health
COMPLETE / PARTIAL / UNKNOWN
native history != reconstructed history
missing evidence is not zero
metrics do not grant send/apply/follow-up authority
```

The test must not require any real personal count.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_metrics_release_contract.py`

Expected: FAIL until README/ROADMAP describe the implemented capability.

- [ ] **Step 3: Update README product section**

Add Search Health as a local reporting capability. Document the canonical commands, aggregate-only JSON, historical provenance boundary and coverage semantics. Do not market it as a success predictor, productivity score, strategy optimizer or proof of causal effectiveness.

- [ ] **Step 4: Update ROADMAP**

Move pipeline reporting from future work into the implemented current slice and keep source/language/strategy comparisons, dashboard UI and actionable-next-state summaries deferred.

- [ ] **Step 5: Run GREEN**

Run:

```bash
pytest -q tests/test_metrics_release_contract.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md ROADMAP.md tests/test_metrics_release_contract.py
git commit -m "docs: document search health reporting"
```

---

### Task 9: Full Verification, PR Review and Merge Gate

**Files:** no new product behavior unless a verification failure requires a tested fix.

**Interfaces:** branch containing the implementation -> `main`.

- [ ] **Step 1: Run the full local test suite**

Run:

```bash
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check main...HEAD
```

Expected: all tests PASS, compile PASS, diff check clean.

- [ ] **Step 2: Run privacy checks explicitly**

Run:

```bash
git ls-files -- \
  'state/history.local.sqlite3*' \
  'state/history-import*.local.json' \
  'artifacts/metrics/**'
```

Expected: no output.

Also inspect `git diff --stat main...HEAD` and ensure no unrelated scoring, send-gate, Gmail mutation, API-route or CV-authority files changed.

- [ ] **Step 3: Open a PR with exact scope/evidence**

Recommended title:

```text
feat: add provenance-aware search health reporting
```

PR body must state: read-only metrics boundary; separate historical store; native precedence; exact-only reconciliation; coverage semantics; no mailbox-wide sync; no new runtime dependency; private August dogfood performed without publishing PII; exact local RED/GREEN/full-suite evidence.

- [ ] **Step 4: Wait for all existing CI jobs on the exact PR head**

Require the repository's pytest, compile, whitespace, private-file guard, recruiter preview, offline runtime build (Python 3.12/3.13), and offline runtime verification jobs to pass. Search Health must not weaken or bypass existing recruiter-runtime acceptance.

- [ ] **Step 5: Review changed files and PR feedback**

No merge with unresolved correctness/privacy feedback. Any behavioral correction gets a failing regression first, then implementation, then focused + full verification.

- [ ] **Step 6: Merge only the verified head**

Use the exact reviewed PR head SHA as the merge expectation. After merge, inspect `main` and the post-merge workflow state before calling the feature complete.

---

## Self-Review Checklist Applied to This Plan

- Spec coverage: contracts, separate historical store, exact reconciliation, read-only native sources, coverage semantics, all approved V1 counts/ratios, CLI+JSON, August dogfood, privacy, docs and CI are each mapped to a task.
- Scope: no UI, API endpoint, multi-user work, strategy ranking, causal claims, automatic follow-up/send, mailbox sync or current-score historical reconstruction was added.
- Type consistency: `Coverage`, `HistoricalObservation`, `MetricFact`, `SourceRead`, `ReconciliationResult` and `SearchHealthReport` are introduced before downstream tasks consume them.
- Privacy: the plan adds both ignore rules and CI tracking guards before any private dogfood run.
- TDD: every production-behavior task begins with a focused RED test, runs the failure, implements the minimum behavior, then runs GREEN before commit.
- Determinism: exact anchors, stable tie-breaks, fixed as-of, sorted JSON and no fuzzy reconciliation are explicit.
