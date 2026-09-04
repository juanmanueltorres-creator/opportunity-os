# Public Contribution Core V1

Public Contribution Core models places where an operator can demonstrate useful work in a public repository without turning repository activity into employment evidence.

## Epistemic boundary

```text
PUBLIC_CONTRIBUTION_ENTRY
= a public repository contribution surface backed by observed evidence or an explicitly labeled hypothesis

PUBLIC_CONTRIBUTION_ENTRY != JOB_OPENING
PR_OPENED != EMPLOYMENT_INTEREST
PR_MERGED != EMPLOYMENT_INTEREST
```

A useful public issue can be observable without being available. A pull request can be opened, reviewed, merged, or closed without implying hiring intent, endorsement beyond that contribution, or permission to contact anyone.

## V1 contract

V1 provides only:

- strict `PublicContributionEntry`, `ContributionEvent`, `ContributionContext`, and `ProofOfWork` models;
- deterministic projection from immutable discovery state plus append-only events ordered by `(observed_at, event_id)`;
- explicit separation of observed needs, maintainer-stated needs, and contribution hypotheses;
- explicit task claim state so `CLAIMED_OTHER` is not treated as actionable availability;
- lifecycle stages from `DISCOVERED` through contribution work and review;
- blocker state that is orthogonal to lifecycle stage;
- PR-only public `ProofOfWork`;
- five sanitized/public dogfood cases.

The contribution funnel is intentionally separate from the hiring funnel.

```text
contribution funnel
repo surface -> task -> work -> PR -> review -> merge/close

hiring funnel
application -> interview -> offer/rejection
```

Contribution funnel metrics remain separate from hiring funnel metrics. A contribution outcome does not imply employment interest.

## Authority boundary

V1 does not add:

- GitHub search or radar automation;
- issue assignment or pull-request creation authority;
- database persistence;
- HTTP API routes;
- Gmail collaboration-response classification;
- Relationship Memory mutation;
- automatic `EvidenceItem` promotion;
- CV generation changes;
- autonomous outreach or follow-up;
- employment-opportunity inference from contribution activity.

Any future bridge from public contribution activity into candidate evidence must remain behind an explicit preview and human-confirmation boundary.
