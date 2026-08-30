# Opportunity OS V0.2B1 — ATS Polished Renderer + Layout QA

Date: 2026-08-29
Status: approved-design / implementation-pending
Base: `main` at `585c1c7bcaf27a5b6e382dbb06169c89ce8adbec`

## 1. Purpose

V0.2B1 upgrades the presentation quality of CV Factory outputs without weakening any of V0.2B's truth, provenance, track-isolation, validation, determinism, ATS, or ApplicationPacket guarantees.

Target flow:

```text
RadarAssessment
→ winning CandidateTrack
→ private MasterFacts
→ EvidenceSelector
→ CVComposer
→ ClaimValidator
→ CVDocumentModel
→ ATS Polished Renderer
→ Layout QA
→ private PDF
→ reproducible ApplicationPacket
```

Invariant:

> Better visual hierarchy may change presentation. It must not change what Opportunity OS is allowed to claim.

## 2. Problem observed in real smoke test

The current `ATSRenderer` is technically valid but visually under-designed:

- headline size is too close to body size;
- section headings do not create enough hierarchy;
- contact/link lines compress visually;
- dense skill blocks read like exported text rather than intentionally designed information;
- projects are not visually distinguished enough from generic body content;
- page utilization can leave a large unused lower area;
- filenames such as `_UPDATED.pdf` look operational rather than application-ready.

The goal is not decorative styling. The goal is a polished, recruiter-readable artifact that still parses safely.

## 3. Scope

V0.2B1 includes:

- a new renderer version, `ats-pdf-v2`;
- stronger typography and spacing while preserving one-column A4 layout;
- a single restrained accent color for non-semantic hierarchy only;
- deterministic horizontal rules/dividers where safe;
- improved section spacing and bullet rhythm;
- differentiated rendering of existing validated headline claim kinds;
- deterministic link rendering as ordinary selectable text;
- `LayoutQA` that evaluates rendered PDF geometry and page utilization;
- professional deterministic output filename generation from candidate + role + company;
- release tests proving ATS and provenance boundaries remain intact;
- a real smoke render using a target application document based on the Scale Up Backend Engineer case.

V0.2B1 excludes:

- photos or avatars;
- company logos;
- two-column layouts;
- sidebars;
- tables for skills or experience;
- semantic icons;
- charts, progress bars, star ratings, skill percentages;
- arbitrary external fonts;
- rasterized text;
- rewriting claims inside the renderer;
- bypassing `ClaimValidator`;
- claiming missing skills such as AWS merely because a vacancy requests them;
- changing evidence selection rules beyond ordering/presentation already allowed by `CVComposer`;
- modifying outreach/send behavior.

## 4. Architectural boundary

Keep semantic truth and rendering strictly separate.

```text
CVDocumentModel
      ↓
validated by ClaimValidator
      ↓
ATSRendererV2
      ↓
RenderedCVArtifact
      ↓
LayoutQA
      ↓
LayoutQAResult
```

`ATSRendererV2` may consume only validated `CVDocumentModel` content.

`LayoutQA` may inspect the rendered artifact and renderer-owned deterministic geometry metrics. It must not rewrite claims or silently mutate content.

If layout QA fails a hard rule, preparation fails using the existing `BLOCKED_RENDER` status. A bounded layout error code may be attached to the failure detail, but no new preparation status is introduced. Partial output is removed according to existing cleanup behavior.

## 5. Renderer V2 visual contract

### 5.1 Page and reading order

- A4 only;
- one text column;
- left-to-right, top-to-bottom reading order;
- no floating text boxes;
- no overlapping elements;
- all visible semantic content remains selectable text.

### 5.2 Typography

Use only built-in deterministic PDF fonts already available to ReportLab:

```text
Helvetica
Helvetica-Bold
```

Recommended hierarchy:

```text
primary identity/name:   17–20 pt
secondary role headline: 10.5–12 pt
section label:           10.5–11.5 pt bold
body:                     9.5–10.2 pt
metadata/contact:         8.8–9.5 pt
```

Exact implementation values must be named constants and regression-tested.

No body text below 9 pt.

### 5.3 Headline claim-kind mapping

V0.2B1 does not add a new semantic model. It uses the existing `CVClaim.kind` values inside the existing `headline` section:

```text
kind=identity  → primary identity/name style
kind=headline  → secondary target-role style
kind=location  → metadata style
kind=contact   → metadata style
kind=link      → metadata/link style
```

Any other claim kind appearing in `headline` falls back to ordinary headline/body-safe styling and does not gain semantic authority.

This mapping changes presentation only. The renderer does not infer a person's name, role, contact information, or target position from free text.

### 5.4 Color

Default semantic text remains black/dark gray.

Renderer may define one restrained accent color for:

- primary identity/name;
- secondary role line;
- section labels;
- divider lines.

Color must never encode information that disappears in grayscale.

### 5.5 Spacing

V2 must visibly separate:

- header from summary;
- section label from section content;
- different experience/project entries;
- bullets from adjacent entries.

The renderer should use whitespace rather than decorative boxes to create hierarchy.

### 5.6 Rules/dividers

A thin deterministic horizontal rule may appear beneath the identity/contact header or between major regions.

Rules are decorative only and may not interrupt text extraction order.

## 6. Content presentation rules

V0.2B1 does not invent new facts. It may improve how validated claims are grouped.

Recommended presentation order remains:

```text
headline
summary
skills
experience
projects
education
languages
links
```

For tech applications, the renderer must support readable skill grouping when the `CVDocumentModel` already contains separate validated claims. The renderer must not parse or split arbitrary prose to manufacture groups.

Experience and project bullets must remain ordinary text paragraphs with deterministic bullet indentation.

## 7. Target-specific positioning

The existing CV Factory remains responsible for selecting the correct evidence pack and wording.

For a backend/AI application, a validated target-specific title such as:

```text
PYTHON BACKEND & GEOSPATIAL SOFTWARE DEVELOPER
```

is preferable to a generic geospatial-heavy headline when supported by existing facts/evidence.

The renderer itself does not decide the target title.

A gap such as AWS remains a gap and must not appear as experience merely because the target posting requests it.

## 8. Professional filename contract

Introduce a deterministic filename helper using sanitized candidate/role/company tokens.

Example:

```text
Juan_Manuel_Torres_Backend_Engineer_Scale_Up.pdf
```

Rules:

- no `_UPDATED`, `_FINAL`, `(1)`, timestamps, random UUIDs, or raw application IDs in the recruiter-facing filename;
- Unicode-normalize then sanitize to a portable filename;
- maximum filename length, including `.pdf`, is 120 characters;
- no path separators or traversal components;
- collapse repeated separators/underscores;
- same semantic candidate/role/company → same filename.

The internal ApplicationPacket may continue to track canonical paths/hashes independently.

## 9. Layout QA

Create a focused component, for example:

```text
app/cv/layout_qa.py
```

with a strict result model similar to:

```text
LayoutQAResult
- valid: bool
- page_count: int
- warnings: tuple[str, ...]
- errors: tuple[str, ...]
- used_height_ratio: float | None
- headline_line_count: int | None
```

Do not expose a raw PDF object dump or arbitrary metadata dictionary.

### 9.1 Hard errors

Layout QA fails closed for:

- zero-page PDF;
- page count above the renderer profile maximum of 2 pages;
- renderer-owned geometry outside configured A4 usable bounds;
- overlapping or invalid frame geometry reported by renderer instrumentation;
- body font configured below 9 pt;
- unresolved renderer exception;
- non-empty validated document yielding no extractable/selectable text in the generated PDF.

### 9.2 Warnings

Warnings do not block V0.2B1.

Initial deterministic warnings:

```text
low_utilization       → one-page used_height_ratio < 0.58
high_utilization      → one-page used_height_ratio > 0.96
headline_wrap         → primary/secondary header region exceeds 3 text lines total
long_unbroken_token   → visible token exceeds configured safe length
```

Orphan and section-density heuristics are deferred; they are not acceptance requirements for V0.2B1.

## 10. Page utilization metric

The current real PDF left substantial unused lower-page area. V2 measures approximate vertical use from renderer-owned layout instrumentation rather than computer vision.

```text
used_height_ratio = rendered_content_height / usable_page_height
```

For one-page output:

```text
< 0.58 → low_utilization warning
> 0.96 → high_utilization warning
```

These are warnings, not truth gates.

For two-page output, V0.2B1 records page count but does not apply a combined utilization threshold.

## 11. Determinism

For fixed:

- validated `CVDocumentModel`;
- renderer version/constants;
- filename inputs;

V2 must produce deterministic bytes and SHA256, preserving the existing reproducibility guarantee.

Do not use current time, random IDs, OS-dependent fonts, network resources, or filesystem metadata in rendering.

## 12. ATS/release contracts

Tests must prove:

1. output remains A4;
2. output remains one-column;
3. only built-in approved fonts are used;
4. text remains selectable/extractable;
5. no images/photos/logos are embedded;
6. no skill bars/charts/tables/semantic icons are introduced;
7. visible claim text comes only from validated `CVDocumentModel` claims;
8. renderer refuses invalid/unvalidated documents exactly as before;
9. renderer does not import private MasterFacts/EvidenceCatalog directly;
10. deterministic document produces deterministic PDF bytes/hash;
11. professional filename is deterministic, sanitized and bounded to 120 characters;
12. layout QA never mutates semantic content;
13. failed hard layout QA leaves no successful ApplicationPacket/PDF artifact;
14. existing track-isolation and claim-validation tests remain unchanged and green.

## 13. TDD strategy

### Task A — Renderer visual constants/contracts

RED tests for:

- `renderer_version == "ats-pdf-v2"`;
- approved fonts only;
- body font floor;
- one-column/A4 invariants;
- deterministic color constants;
- validated-document gate remains mandatory.

### Task B — Header and section hierarchy

RED tests for deterministic story/style specification:

- `identity`, `headline`, `contact/location/link` use distinct approved styles;
- primary identity is materially larger than body;
- section labels are visually distinct;
- divider is deterministic and non-semantic;
- spacing constants prevent collapsed sections.

### Task C — Layout QA

RED tests for:

- one-page healthy fixture;
- low-utilization warning at `< 0.58`;
- high-utilization warning at `> 0.96`;
- headline-wrap warning above 3 header lines;
- missing extractable text hard failure;
- page count above 2 hard failure;
- no semantic mutation.

### Task D — Filename

RED tests for:

- sanitized role/company;
- no `_UPDATED`/`FINAL` suffix patterns;
- deterministic output;
- maximum 120 characters;
- path-safe output.

### Task E — Integration

- CV preparation invokes renderer V2 then Layout QA;
- hard layout failure maps to existing `BLOCKED_RENDER`;
- hard layout failure removes the partial PDF;
- valid layout preserves existing `cv_sha256` / packet semantics;
- full regression suite remains green.

### Task F — Real smoke render

Generate a private PDF from a verified backend-oriented document using existing evidence from the Scale Up-style target case.

Inspect:

- visual hierarchy;
- page balance;
- contact/link readability;
- project readability;
- selectable text;
- filename;
- no unsupported AWS claim.

The smoke PDF is not committed if it contains private user data.

## 14. Expected files

Likely changes:

```text
app/cv/renderer.py
app/cv/layout_qa.py
app/cv/models.py            # only bounded result/config models if needed
app/cv/service.py           # invoke layout QA
app/cv/filename.py          # focused filename helper
README.md
ROADMAP.md
tests/test_cv_renderer.py
tests/test_cv_layout_qa.py
tests/test_cv_filename.py
tests/test_cv_factory_integration.py
tests/test_cv_release_contract.py
```

Avoid unrelated refactors.

## 15. Acceptance criteria

V0.2B1 is complete when:

1. CV output looks intentionally designed rather than like a raw text export;
2. ATS invariants remain one-column, selectable-text, A4, standard-font and parser-safe;
3. renderer never changes semantic claims;
4. `ClaimValidator` remains the hard semantic gate;
5. Layout QA returns deterministic hard errors/warnings and blocks only hard failures;
6. one-page page utilization is measured with exact warning thresholds `0.58 / 0.96`;
7. recruiter-facing filename is professional, path-safe and deterministic;
8. fixed input produces deterministic bytes/hash;
9. existing CV Factory provenance/track/application packet tests remain green;
10. real backend-target smoke PDF contains only verified evidence and no fabricated AWS experience;
11. full tests, compile check, diff check and private/generated-file guard pass.

## 16. Future work

Not part of V0.2B1:

- second visual theme;
- two-page senior profile tuning beyond the 2-page hard ceiling;
- company-branded variants;
- browser/HTML renderer;
- generative design selection;
- visual screenshot scoring with computer vision;
- automatic content rewriting to fit a page;
- auto-dropping experience solely to satisfy a layout target;
- orphan/section-density heuristics.

Those should only be considered after V2 is validated on real applications.

## 17. Final boundary

```text
VERIFIED FACTS / EVIDENCE
        ↓
CV COMPOSER
        ↓
CLAIM VALIDATOR
        ↓
POLISHED RENDERER
        ↓
LAYOUT QA
        ↓
APPLICATION PACKET
```

Still true:

```text
DESIGN ≠ EVIDENCE
LAYOUT ≠ CLAIM AUTHORITY
TARGET KEYWORD ≠ EXPERIENCE
POLISHED ≠ ATS-UNSAFE
```
