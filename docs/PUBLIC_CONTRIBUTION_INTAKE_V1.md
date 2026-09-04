# Public Contribution Intake V1

Contribution Intake / Observation Bridge V1 turns one explicitly selected public GitHub issue or pull request into a typed local preview. The operator reviews that exact preview before any local contribution state is written.

## Safety and authority boundary

GitHub reads are explicit and read-only.

Preview is local and non-mutating.

Import mutates only local contribution state after confirmation.

No GitHub write authority is added.

Contribution outcomes do not imply employment interest.

V1 is explicit-resource intake, not discovery/radar.

The contribution funnel remains separate from the hiring funnel. A public issue, assignment, review, opened pull request, merged pull request, or external blocker is contribution evidence only. It does not imply recruiting intent, hiring authority, contact permission, or a job opening.

## Operator flow

```text
explicit GitHub issue / PR
        ↓
read-only public snapshot
        ↓
typed ContributionObservation
        ↓
deterministic zero/one proposal
        ↓
hash-bound preview
        ↓
human confirmation
        ↓
local PublicContributionEntry or ContributionEvent
```

Preview does not initialize the local contribution database. Confirmed import is the only CLI path that initializes or writes contribution persistence.

## CLI

Preview one explicit public GitHub resource:

```bash
python -m app.contributions.intake_cli preview \
  --url https://github.com/owner/repo/issues/123 \
  --operator-login your-github-login \
  --out contribution-preview.json
```

A pull request requires explicit contribution lineage:

```bash
python -m app.contributions.intake_cli preview \
  --url https://github.com/owner/repo/pull/456 \
  --operator-login your-github-login \
  --entry-id contrib-existing-entry \
  --out contribution-preview.json
```

After reviewing an `IMPORTABLE` preview, confirm it explicitly:

```bash
python -m app.contributions.intake_cli import \
  --preview-file contribution-preview.json \
  --confirmed-by operator-id
```

Both commands accept an optional `--db` path. The default local persistence path is:

```text
state/contributions.local.sqlite3
```

That database and its SQLite sidecars are local-only and gitignored.

## V1 evidence rules

- Existing issue lineage requires exact repository identity and exact `task_ref` equality.
- Pull requests always require an explicit existing contribution entry; PR body text such as `Closes #25` does not establish authoritative lineage.
- A preview proposes at most one new entry or one contribution event.
- Pull-request facts are consumed in public chronology before terminal state.
- Generic CI failure is not an external blocker.
- Only bounded authorization/access evidence may project `EXTERNAL_AUTHORIZATION_REQUIRED`.
- Import revalidates the exact embedded typed preview against current local state and performs no GitHub read.
- A changed local history invalidates the old preview rather than silently applying it.

## Explicit non-goals

V1 does not provide:

- GitHub search, repository radar, or automatic discovery;
- background polling or monitoring;
- issue assignment or claiming;
- GitHub comments, review submission, pull-request creation, update, close, or merge;
- Gmail collaboration-response classification;
- Relationship Memory mutation;
- Outreach or CV integration;
- automatic `ProofOfWork` or candidate `EvidenceItem` promotion;
- HTTP API routes;
- employment or hiring inference from contribution activity.

The V1 authority boundary is intentionally narrow: observe one explicit public resource, preview one bounded local transition, and require human confirmation before local import.
