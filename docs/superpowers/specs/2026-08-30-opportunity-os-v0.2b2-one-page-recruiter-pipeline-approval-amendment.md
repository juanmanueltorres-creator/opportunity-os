# Opportunity OS V0.2B2 — Approval Amendment

Date: 2026-08-30
Status: approved
Applies to: `2026-08-30-opportunity-os-v0.2b2-one-page-recruiter-pipeline-design.md`

The V0.2B2 One-Page Recruiter CV Pipeline design is approved for implementation.

This approval fixes the following normative decisions:

- recruiter-facing canonical CV output is exactly one A4 page;
- there is no automatic two-page fallback;
- `ClaimValidator` remains the semantic authority before recruiter-specific grouping;
- `RecruiterDocumentComposer` may only select, order, group or omit already validated claims;
- `RecruiterDocumentValidator` must reject any unvalidated candidate-specific claim reference;
- skills are grouped into compact recruiter rows rather than rendered one atomic paragraph per skill;
- the default recruiter profile is capped at four projects and one visible bullet per included experience entry;
- body text may not be reduced below 9 pt to force fit;
- a second page or unresolvable overflow is a hard `BLOCKED_RENDER` failure;
- Opportunity OS remains the owning repository and semantic authority;
- RenderCV/Typst may be used behind an internal renderer adapter, with a ReportLab fallback permitted only if it satisfies the same acceptance contract;
- normal preparation must work offline once dependencies are installed;
- a fresh agent/operator must use the canonical documented entrypoint rather than reconstructing CV generation from chat memory;
- `PREPARED != APPROVED != SENT` remains unchanged.

No SEND authority is introduced by this approval.