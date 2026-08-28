# Opportunity OS

Open-source opportunity discovery, normalization, matching, and application-preparation infrastructure with **explainable scoring and human approval**.

Opportunity OS is deliberately not an auto-apply bot. The V0.1 system helps a person discover and evaluate opportunities while keeping consequential actions under human control.

## V0.1 capabilities

- FastAPI service with versioned read/assessment contracts.
- Public job ingestion from Remotive.
- Public ATS adapters for Greenhouse, Lever, and Ashby.
- One normalized `Opportunity` domain model across sources.
- SQLite persistence with source-aware deduplication.
- Local YAML candidate profiles.
- Deterministic, explainable matching.
- Strengths, gaps, risks, evidence, and recommendation in every assessment.
- Typed connector failures with public-safe API errors.
- Offline test suite: connector HTTP calls are mocked.

## What V0.1 does not do

Opportunity OS does **not**:

- submit applications or CVs;
- send recruiter messages;
- scrape LinkedIn or Indeed;
- automate browser interactions;
- bypass CAPTCHAs or anti-bot controls;
- store job-portal passwords;
- answer legal or declarative application questions;
- use an LLM to invent experience or determine the match score.

The product boundary is intentional: automate repetitive research and preparation, not identity-bearing decisions.

## Architecture

```text
Authorized public source
        ↓
Source adapter
        ↓
Normalized Opportunity
        ↓
SQLite repository + deduplication
        ↓
Candidate profile
        ↓
Deterministic matcher
        ↓
Explainable assessment
        ↓
Human decision
```

Source-specific payloads stay inside connectors. Business logic does not depend on raw ATS JSON.

## Sources

V0.1 includes adapters for:

- **Remotive** — exposed through the HTTP ingestion endpoint.
- **Greenhouse Job Board API** — public GET job-board data.
- **Lever Postings API** — public published postings.
- **Ashby Public Job Posting API** — public job-board postings; unlisted postings are excluded from discovery.

Source identifiers such as Greenhouse board tokens, Lever site names, and Ashby board names are public routing identifiers, not credentials.

### Remotive attribution

If you display Remotive-sourced opportunities, follow Remotive's public API terms: preserve the original Remotive URL and identify Remotive as the source. Opportunity OS stores the original `source_url` so downstream consumers can preserve provenance.

## Quick start

Requires **Python 3.12+**.

```bash
python -m venv .venv
# Activate .venv for your shell/operating system.
python -m pip install -e ".[dev]"
cp profiles/example_profile.yaml profile.local.yaml
uvicorn app.main:app --reload
```

Run the test suite:

```bash
python -m pytest -v
```

The tests do not require live job-board access.

## Local configuration

`.env.example` documents the current local settings:

```text
OPPORTUNITY_DB_PATH=opportunities.db
OPPORTUNITY_PROFILE_PATH=profile.local.yaml
HTTP_TIMEOUT_SECONDS=10
```

`profile.local.yaml`, `.env`, and local SQLite files are ignored by Git. The repository ships only a fictional example profile.

## HTTP API

Health:

```text
GET /health
```

Opportunities:

```text
GET /api/v1/opportunities
GET /api/v1/opportunities/{id}
```

Remotive ingestion:

```text
POST /api/v1/ingest/remotive
```

Assessment:

```text
POST /api/v1/assessments/{opportunity_id}
```

The assessment response includes the overall score plus component scores, strengths, gaps, risks, selected verified evidence, recommendation, and explanation. A percentage alone is never treated as sufficient evidence.

## Company ATS adapters

Greenhouse, Lever, and Ashby are V0.1 library adapters. They can be composed with the same repository and ingestion service without adding new business logic.

Example with Greenhouse:

```python
import asyncio
import httpx

from app.connectors.greenhouse import GreenhouseConnector
from app.repositories.opportunities import SQLiteOpportunityRepository
from app.services.ingestion import ingest


async def main() -> None:
    repository = SQLiteOpportunityRepository("opportunities.db")
    repository.initialize()

    async with httpx.AsyncClient() as client:
        connector = GreenhouseConnector(
            client,
            board_token="example-company",
            company_name="Example Company",
        )
        result = await ingest(connector, repository)
        print(result)


asyncio.run(main())
```

Use the equivalent `LeverConnector` or `AshbyConnector` for those sources.

## Explainable scoring

The V0.1 score is deterministic:

| Component | Weight |
| --- | ---: |
| Core / mandatory skill fit | 40% |
| Domain fit | 20% |
| Verified evidence fit | 20% |
| Location / remote fit | 10% |
| Freshness | 10% |

Matching is intentionally conservative. Similar-looking technologies are not silently treated as equivalent, and unverified evidence does not increase evidence fit.

Recommendations are one of:

```text
apply
stretch
nurture
discard
```

Hard incompatibilities remain visible as risks instead of being hidden by a high aggregate score.

## Safety and privacy defaults

- no committed credentials;
- no public personal candidate profile;
- no public CV by default;
- no portal password storage;
- explicit HTTP timeouts;
- connector failures do not truncate existing opportunities;
- external source errors are sanitized before reaching API clients;
- consequential external actions remain outside V0.1.

## Development

The implementation is intentionally incremental. Domain models, connectors, storage, matching, and HTTP composition are separate boundaries so each can evolve without refactoring the whole application.

Design and implementation plan:

```text
docs/superpowers/specs/2026-08-28-opportunity-os-v0.1-design.md
docs/superpowers/plans/2026-08-28-opportunity-os-v0.1.md
```

## License

MIT
