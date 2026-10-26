# LATAM + Cordoba Opportunity Discovery — V1

Status (2026-10-25): **source inventory registered, collectors not implemented**.

This document defines a small extension of the existing Opportunity OS. It does not create a second application. The canonical catalog is `config/source_catalog.yaml`. Its entries classify evidence authority, **not** whether a connector currently runs. Only `remotive`, `greenhouse`, `lever` and `ashby` are currently implemented as remote collectors.

## Source inventory and operational boundaries

| Source key | Public entry point | Treatment |
| --- | --- | --- |
| startupjobs_ar | https://www.startupjobs.ar/empleos | Aggregator: discover then verify at original employer |
| startupjobs_cl | https://www.startupjobs.cl/ | Aggregator: remote Chile != work authorized from Argentina |
| startupjobs_mx | https://www.startupjobs.mx/empleos | Aggregator: remote Mexico != work authorized from Argentina |
| derecruiters | https://www.derecruiters.com/ | Recruiter job listings: verify role and eligible countries |
| remotos_latam | https://remotoslatam.com/empleos | Aggregator: verify original |
| alerta_empleo_remoto | https://empleos.buscoempleoremoto.com/ | Aggregator: verify original and deduplicate |
| cordoba_startup_monitor | https://corlab.cordoba.gob.ar/startup-cordoba-monitor/ | **Target accounts**, not vacancy records |
| innovab_cordoba | https://innovab.cordoba.gob.ar/ | Startup/innovation discovery; distinguish calls, events and employment |
| cordoba_cluster | https://cordobacluster.com/ | **Target accounts**, not vacancy records |
| unc_geologia | https://fcefyn.unc.edu.ar/facultad/secretarias/secretaria-de-graduados/portal-de-empleo/geologia/ | University job notices: verify still open |
| geodojo | https://geodojo.ai/empleos | Geo job discovery; verify actual listed position and employer |
| geoinquietos_ar | https://www.osgeo.org/local-chapters/osgeo-argentina/ | Community signal only; no automated private group access |
| frontendcafe | https://frontend.cafe/ | Community signal only; no automated private Discord access |
| devschile | https://devschile.cl/ | Community signal only; no automated private Slack access |
| cuti_uruguay | https://cuti.org.uy/ | Sector ecosystem / company discovery |
| uruguay_xxi | https://www.uruguayxxi.gub.uy/es/directorio-servicios/ti/ti-1/ | Company directory / target accounts |
| ycombinator_jobs | https://www.ycombinator.com/jobs/ | Job board; many remote roles are country-restricted |
| reddit | https://www.reddit.com/r/empleos_AR/ and https://www.reddit.com/r/Cordoba/ | Already in catalog; community signal, not automatically a verified vacancy |
| getonboard | https://www.getonbrd.com/ | Already in catalog; check eligibility country at original listing |

## Collection principles

1. Prefer public official ATS/API/RSS feeds, then sitemap, then narrowly scoped public HTML spiders using Scrapy **only after** checking permissions, robots directives and terms. No CAPTCHA bypass, authentication harvesting, proxy evasion or private channel scraping.
2. Each collector is independently toggleable and rate-limited, with bounded response size, polite backoff, user agent, timestamps, page limits, safe redirects and domain allowlist. A failed source must not fail the batch.
3. Discovery index / community signals may create *review candidates*, not automatically `ACTIVE_POSTING`. Direct official job detail URL and active-status evidence must be checked first.
4. Company directories populate **Target Accounts** separately, never the job posting table. Anonymous community discussion is not proof of hiring.
5. Persist only public metadata: original job URL, employer, title, location text, source, first seen, last seen, posting date if known, evidence snippets and explicit verification status. Do not store job-description copies unnecessarily or publish private candidate/outreach history.
6. Deduplicate by original ATS ID/canonical URL when available, falling back to conservative title + normalized employer + location. Never collapse distinct vacancies solely by title.

## Crucial geography and language semantics

**Never** equate posting / employer location with countries from which the company will hire.

- `company_country`: office / headquarters.
- `workplace_country`: office or expected country for on-site/hybrid.
- `remote_mode`: `REMOTE`, `HYBRID`, `ONSITE`, `UNKNOWN`.
- `eligible_countries`: declared countries where remote work is allowed; an empty list is **unknown**, not worldwide.
- `eligible_from_argentina`: `YES`, `NO`, `UNKNOWN`, derived only from clear eligibility evidence (e.g. 'LATAM' expressly includes Argentina unless listing excludes it; 'remote Chile' alone does not).
- `posting_language`: detected written listing language (weak clue).
- `working_language`: `ES`, `EN`, `BILINGUAL`, `UNKNOWN`, derived from explicit requirements, **not** inferred from Spanish listing.
- `date_published`, `date_discovered`, `date_last_verified`: independent dates. Unknown publication date must remain unknown.
- `already_applied`: derive from **private** application/relationship ledger, never a public scraper result.

Filter default: `eligible_from_argentina=YES` and `remote_mode=REMOTE`, allow `UNKNOWN` in a separate review lane, exclude known English-mandatory roles if user requests Spanish-only. Include on-site/hybrid Córdoba and geoscience San Juan as distinct opt-in tracks.

## Minimal build sequence (not completed by this catalog-only PR)

1. **Collectors (small first slice):** validate allowed access to StartupJobs Argentina, de/Recruiters and UNC Geología; use a source-specific adapter only if published public content can be fetched compliantly. Add fixtures + parser tests. Normalize discovery candidates to the existing existing ingestion/review boundary.
2. **Search API:** add explicit filters to existing `GET /api/v1/opportunities` (source, role keyword, last seen, verified status, remote mode, eligible-from-Argentina, Spanish work language and not already applied). Keep the unfiltered endpoint compatible.
3. **Daily execution:** scheduled worker (e.g. GitHub Actions or hosted cron), persistent storage with a verified backup. **GitHub Actions ephemeral SQLite is not durable**: use protected persistent database or safe public-only structured artifact. No credentials in public repo.
4. **Single lightweight web UI:** read existing FastAPI route; filters + two lanes `Verificadas` and `Por comprobar`; show original apply URL and evidence, never invented recruiter email.
5. **ChatGPT workflow:** read from the same up-to-date data source via an authorized connected app/API; explicitly state last refresh and unavailable feeds. The local SQLite file is not automatically accessible to ChatGPT in future chats.

## Minimum acceptance criteria

- "Remoto México" without explicit hiring eligibility never appears as confirmed Argentina-eligible.
- A Spanish description without language requirement never becomes confirmed Spanish-only.
- Duplicate employer listing via two aggregators appears once, keeping both source observations.
- Startup directory entries do not count as job openings.
- A stale/non-accessible posting is marked for re-verification; absence from one fetch does not prove closure.
- Previously sent applications are excluded by exact private ledger reconciliation without pushing sensitive CRM records to public GitHub.
- Failed or blocked sources show a last-refresh error, not a fabricated zero results count.
- No external applications or emails occur without explicit user action.

## Product scope

This is a job search aid, not an auto-apply bot. Prioritize actionable new positions and eliminate daily manual link checking. Avoid a new authentication system, broad scraping engine or separate dashboard backend. Build incrementally on existing FastAPI + Opportunity Radar.
