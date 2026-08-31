# CV Attachment Selection

## Attachment selection contract

A recruiter CV used for outreach is not selected by resemblance, filename, recency, or prior batch history. It is selected by the canonical Opportunity OS application lineage.

Never resolve a CV attachment by filename, fuzzy Library search, `latest`, a same-named PDF, or a previously generated batch artifact.

For an active-posting application, the only allowed attachment source is the exact artifact referenced by the current `ApplicationPacket` and propagated into `OutreachBrief.cv_pdf_path`.

Before outreach becomes ready, Opportunity OS must verify all of the following:

- the packet belongs to the same opportunity, selected intent, and application track;
- the packet language contract is valid;
- `renderer_version` is an outreach-allowed recruiter renderer; currently this is `rendercv-typst-v1`;
- the exact PDF at `cv_pdf_path` exists;
- the bytes at that path hash exactly to the packet `cv_sha256`;
- the draft contains exactly one CV attachment whose hash matches that same `cv_sha256`.

A legacy renderer such as `ats-pdf-v2` is not interchangeable with the current recruiter artifact merely because the candidate, company, or filename looks correct. It must fail closed before outreach preparation.

If the canonical artifact is missing, inaccessible, changed, or from a disallowed renderer, stop. Regenerate the application through the canonical preparation pipeline. Do not substitute another PDF from Library and do not hand-build a replacement.

This contract intentionally makes duplicated filenames harmless: identity comes from packet lineage plus content hash, not the basename.

For speculative target-account outreach, do not invent an `ApplicationPacket` for a vacancy that does not exist. Use the target-account workflow and produce any recruiter artifact through its explicit canonical preparation path before attachment.
