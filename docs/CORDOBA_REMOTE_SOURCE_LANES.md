# Opportunity OS — Córdoba / Argentina remote lanes (2026-10-26)

## User decision rule

Default job-search location is **Córdoba, Argentina**. Jobs may qualify in one
of two ways, without treating "remote" as synonymous with "hire from anywhere":

1. `REMOTE_ARGENTINA`: explicitly remote AND location eligibility explicitly
   names Argentina or LATAM. Manual employer/ATS verification still required.
2. `CORDOBA_LOCAL`: explicit Córdoba location AND onsite/hybrid modality.
   Confirm the actual workplace is Córdoba Capital or commutable before applying.

Separate `REVIEW` lane: remote but eligibility unknown (e.g. "Worldwide",
"Remote México" without Argentina authorization), or Córdoba location without
explicit modality.

Excluded from default shortlist: onsite/hybrid Buenos Aires, Rosario,
San Juan, Mendoza or other locations; foreign-country-restricted remote jobs;
and roles explicitly requiring advanced English for the working team. Foreign
Córdoba (Spain) must not be treated as Argentina.

Unknown work language stays UNKNOWN (not automatically English or Spanish).
English mandatory is excluded; unknown language needs manual review.
Do not deduce eligible country from company HQ or language of listing.

The daily GitHub Actions report outputs:

- `matches`: selected, geographically eligible jobs, <=35;
- `needs_review`: unknown eligibility, <=20;
- `geographic_filter`: deterministic filter policy identifier;
- `sources`: source-by-source collection diagnostics.

Only selected `matches` are optionally persisted to Supabase. Review entries
are **not** silently treated as active vacancies. All listings have
`verification_status=PENDING` until manually verified.

## Under-the-radar source lanes

**Actual collection, six public API/feeds:** Remotive, Get on Board, Jobicy,
Himalayas, Remote OK, Arbeitnow. Their output may be empty, rejected or
limited; use the report source diagnostics, not assumed availability.

**Public niche boards / directories, discovery only until collector exists:**

- StartupJobs Argentina: https://www.startupjobs.ar/empleos
- GeoDojo GIS notices: https://geodojo.ai/empleos
- Córdoba Startup Monitor (company discovery, not a vacancy board):
  https://corlab.cordoba.gob.ar/startup-cordoba-monitor-actualizado/
- Geología UNC / secretaría de graduados:
  https://fcefyn.unc.edu.ar/facultad/secretarias/secretaria-de-graduados/portal-de-empleo/geologia/
- de/Recruiters: https://www.derecruiters.com/
- FrontendCafé (Spanish-language public community; Discord participation
  requires user's own membership): https://frontend.cafe/
- Geoinquietos Argentina: https://www.osgeo.org/local-chapters/osgeo-argentina/
- devsChile: https://devschile.cl/

**Public Reddit employment signals, not verified opportunities:**

- r/devsarg recurring offers threads: https://www.reddit.com/r/devsarg/
- r/empleos_AR: https://www.reddit.com/r/empleos_AR/
- r/Cordoba: https://www.reddit.com/r/Cordoba/

These three subreddit niches are separate `COMMUNITY_SIGNAL`,
`DISCOVERY_ONLY` catalog entries for future manual/bounded review. Never
scrape closed Telegram, WhatsApp, Discord or Slack groups. Never fabricate a
job requisition from informal posts; verify employer, posting, original
application URL, location, work-country and language before an APPLICATION.

## Remaining wiring

This branch improves the daily job radar **filter and report**. It does NOT
implement public HTML collectors for communities, API route query parameters,
a dedicated UI, or a scheduled private Gmail-Supabase sync. The Supabase
`sources.connector_status` field is not a reliable live GitHub Actions
health signal until a diagnostic sync exists: do not mark sources CONFIGURED
without a verified collector.

Run before merging:

```bash
python -m pytest tests/test_daily_job_radar.py tests/test_cordoba_filters.py tests/test_latam_source_catalog.py
```

Then run GitHub Actions workflow manually, inspect `jobs.json` and `jobs.md`,
and check that a Buenos Aires onsite listing is excluded, an explicitly
Argentina-eligible remote job is recommended, and "Worldwide" appears only
under review.

No changes to the private application/contact/CRM tables or outbound emails.
