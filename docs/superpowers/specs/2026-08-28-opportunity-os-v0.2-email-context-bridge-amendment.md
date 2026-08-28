# Opportunity OS — V0.2 Email-First Outreach + Context Bridge Amendment

Date: 2026-08-28
Status: review
Applies to: V0.2 roadmap and follow-on slices after V0.2A

## 1. Product decision

Opportunity OS should prefer a **direct, personalized email path** when a legitimate company/recruiter contact can be identified, instead of forcing every opportunity through a repetitive hosted application form.

The system must also expose a compact **Context Bridge** so ChatGPT can inspect current Opportunity OS state from a small curated snapshot and only fetch Gmail/GitHub details on demand.

These two capabilities reduce repeated manual work without turning Opportunity OS into a bulk-spam or autonomous identity system.

## 2. Email-first principle

Application channel priority is:

```text
1. direct published application email
2. verified corporate recruiter / talent-acquisition email
3. authorized applicant-side API
4. form assist
5. hosted manual form
6. restricted/manual platform
```

Email is preferred only when the address is plausibly relevant to the role/company. The system must not manufacture guessed addresses and must not contact unrelated people merely to increase volume.

## 3. Contact source hierarchy

A contact may come from:

```text
job_posting
company_careers_page
company_recruiting_page
existing_email_thread
approved_contact_database
manual_user_input
```

For an approved contact database such as Apollo:

- search may identify relevant recruiting/talent contacts;
- revealing/enriching contact data may consume provider credits and therefore remains an explicit optional action;
- prefer verified corporate/work email addresses;
- personal/private email enrichment is not required for V0.2;
- provider-specific sending sequences are not a core dependency.

Opportunity OS never requires Apollo to function.

## 4. Outreach contact model

```text
OutreachContact
- id
- company
- person_name optional
- role_title optional
- email
- email_kind: corporate | published_application | unknown
- source
- source_url optional
- verification_status
- relevance_reason
- discovered_at
```

`relevance_reason` is mandatory when the target is a person rather than a generic published application inbox.

Examples:

```text
"Talent Acquisition Partner at the hiring company"
"Recruiter listed on the vacancy"
"Application address published on the company's careers page"
```

## 5. Email application packet

The later CV Factory / Application Packet slice should produce:

```text
EmailApplicationPacket
- opportunity_snapshot
- assessment_snapshot
- selected_contact
- personalized_cv_artifact
- subject
- body
- attachment_manifest
- unresolved_questions[]
- profile_version
- scoring_version
- template_version
- packet_hash
```

The message must be generated only from verified facts/evidence.

## 6. Message design

Default job-outreach email should be short and role-specific.

Target structure:

```text
why this role/company
+ 1-2 strongest relevant facts/evidence
+ CV attached
+ one clear CTA
```

Avoid:

- generic long cover letters by default;
- invented familiarity with the recruiter/company;
- fake metrics;
- claims not present in verified profile/evidence;
- mass-identical wording across unrelated roles.

Personalization should alter evidence selection and wording, not candidate truth.

## 7. Gmail as the initial execution layer

Do not add Google OAuth credentials to the public Opportunity OS backend merely to send mail.

Initial execution model:

```text
Opportunity OS
  -> produces EmailApplicationPacket metadata + private CV artifact reference
  -> Context Bridge exposes pending packet to ChatGPT
  -> ChatGPT uses the user's authorized Gmail connector
  -> create/review draft
  -> send only after explicit user authorization
```

This keeps email credentials outside Opportunity OS and reuses an already-authorized user channel.

Gmail-side capabilities expected from the operator layer:

- search/read relevant job/recruiter threads;
- create draft;
- update draft;
- attach the approved CV artifact;
- send an explicitly approved draft/message;
- search replies later for follow-up/status updates.

## 8. Batch behavior

The product goal may be up to 20 quality applications/day, but email outreach must remain bounded by quality rules.

Default safeguards:

```text
max applications/day: 20
max contacts for one requisition: 1 initially
max recruiters contacted at one company/day: 2
no duplicate recipient + requisition
no repeated initial email after confirmed delivery
follow-up only from explicit history policy
```

Do not contact additional recruiters for the same role simply to hit the daily cap.

## 9. Form fallback

Email-first does not mean forms disappear.

Use form/application URL when:

- the employer explicitly requires the official form;
- no relevant contact is available;
- the email is only a general inbox with no recruiting relevance;
- the application includes mandatory structured/legal questions;
- a recruiter directs the candidate to the formal process.

If both email and official form are useful, the system may recommend:

```text
submit official form
+ send short recruiter note referencing the application
```

but it should not duplicate CV submissions without a reason.

## 10. Context Bridge goal

ChatGPT should be able to answer questions such as:

```text
"what should I apply to today?"
"what emails need a reply?"
"prepare the top 5"
"what happened with company X?"
"reply to that recruiter"
```

without reloading the full vault, inbox, repository, and application history every time.

Opportunity OS therefore maintains a compact private context snapshot.

## 11. Curated context contract

Conceptual snapshot:

```text
OpportunityContextSnapshot
- generated_at
- snapshot_version
- profile_fingerprint
- active_goal_summary
- radar_summary
- prioritized_opportunities[]
- active_applications[]
- pending_email_actions[]
- interview_actions[]
- followups_due[]
- recent_outcomes[]
- source_health
- scoring_version
```

Each item is concise and references stable IDs/URLs instead of embedding entire job descriptions or email bodies.

Example opportunity entry:

```text
opportunity_id
company
title
career_match
income_viability
confidence
tier
recommended_action
application_mode
contact_id optional
application_id optional
```

## 12. Progressive retrieval rule

The snapshot is an index, not a copy of all personal data.

Operator flow:

```text
read context snapshot
  ↓
identify exact opportunity/application/thread
  ↓
fetch only required detailed source
  - Opportunity OS/GitHub state
  - one Gmail thread
  - one CV/application artifact
```

This minimizes repeated context loading and keeps decisions grounded in current source data.

## 13. Storage boundary

Public `opportunity-os` repository contains:

- schemas;
- snapshot generator contract;
- fictional examples;
- tests.

Private state contains:

- actual application status;
- real contacts/email addresses;
- CV artifact paths;
- email/thread identifiers;
- personal profile fingerprint;
- follow-up notes.

Private snapshot may live in the existing private knowledge vault initially. A later database-backed representation may replace it without changing the operator contract.

## 14. Inbox curation

The Context Bridge may maintain derived mail state such as:

```text
needs_reply
waiting
interview
rejected
offer
informational
unknown
```

It should store a short derived summary and Gmail message/thread identifier, not a full mailbox mirror.

Suggested Gmail labels are optional UI aids, not a source of truth.

## 15. Human-control boundary

Safe automatic preparation:

- find/rank opportunities;
- identify plausible recruiting channel;
- select verified evidence;
- generate CV draft/artifact;
- draft a personalized email;
- identify follow-up candidates;
- curate the context snapshot.

Requires explicit user authorization before external representation:

- sending a new job/recruiter email;
- sending a reply;
- submitting a form;
- attaching a changed CV after prior approval;
- sending salary/legal/declarative answers.

A later batch approval may authorize an exact set of immutable email packets, but no generic standing permission is assumed by this amendment.

## 16. Operator workflow from ChatGPT

Desired interaction:

```text
User: "chef, qué hay hoy?"

ChatGPT:
1. reads OpportunityContextSnapshot
2. retrieves details only for top/relevant items
3. surfaces actions

User: "prepará las primeras 5"

ChatGPT / Opportunity OS:
1. builds/reads exact application packets
2. creates personalized CVs
3. creates Gmail drafts
4. reports exceptions

User: "mandá esas 5"

ChatGPT:
1. verifies draft recipients/attachments against approved packets
2. sends the exact approved drafts
3. updates application state/context snapshot
```

The context snapshot must never itself be treated as authorization to send.

## 17. Response tracking

Gmail can be used as a source for detecting replies after an application.

Derived events:

```text
reply_received
interview_requested
additional_information_requested
rejection_received
offer_or_next_stage
unknown_reply_needs_review
```

Classification may be automated for triage, but consequential interpretations/actions remain reviewable.

## 18. Implementation placement

Do not bloat V0.2A Radar with mail sending.

Recommended sequencing:

```text
V0.2A Radar
  - emits application_mode + contact-discovery hint
  - emits compact radar snapshot data

V0.2B CV Factory
  - produces personalized CV + immutable packet

V0.2C Email-first Approval + Submission
  - contact resolution
  - Gmail draft/send operator contract
  - form fallback

V0.2E Context Bridge
  - compact OpportunityContextSnapshot
  - Gmail-derived action summaries
  - operator retrieval contract
```

The snapshot schema should be designed early enough that each slice emits stable IDs/version metadata.

## 19. Definition of done for email-first path

A user can:

1. select a scored opportunity;
2. resolve a legitimate application/recruiter email when available;
3. generate a CV tailored only from verified evidence;
4. generate a concise personalized email;
5. create a Gmail draft with the correct CV attached;
6. review it from ChatGPT/Gmail;
7. explicitly authorize send;
8. send from the connected mailbox;
9. later detect the reply and relate it to the same opportunity/application;
10. fall back safely to official/manual form when email is not appropriate.

## 20. Definition of done for Context Bridge

From a new ChatGPT conversation, the operator can read one compact private snapshot and determine:

- current search intent;
- highest-priority opportunities;
- applications in progress;
- email actions requiring attention;
- interviews/follow-ups;
- stable IDs needed to retrieve deeper source context;

without loading the entire historical vault or mailbox.

## 21. Constraints

- no guessed recruiter emails;
- no scraping LinkedIn inbox/profiles for contact data;
- no bulk spam;
- no personal-email enrichment requirement;
- no external send without explicit approval;
- no full Gmail mirror in Opportunity OS;
- no secrets/CVs/real contacts committed to the public repo;
- no duplication of candidate facts across personalized CVs/messages;
- Context Bridge stores references + curated state, not uncontrolled raw history.
