"""Small, bounded list of verified public employer ATS boards.

Employer job listings are not equivalent to Argentina eligibility. The radar
ranks them conservatively and the public UI labels unverified overseas roles.
No scraping, login, paid datasets or third-party API key required.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from app.connectors.ashby import AshbyConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.models.domain import Opportunity

# Verified employer-owned job boards (public job listing pages).
# Add a company only after confirming its real ATS board URL.
TARGET_BOARDS = (
    ("greenhouse", "ardentmc", "Ardent"),
    ("greenhouse", "blackcanyonconsulting", "Black Canyon Consulting"),
    ("greenhouse", "tinginternet", "Ting Internet"),
    ("ashby", "civilgrid", "CivilGrid"),
    ("ashby", "agzen", "AgZen"),
    ("ashby", "klim", "Klim"),
    ("ashby", "finagra", "FinAgra"),
    # Public company ATS boards observed in Argentina/LATAM for geospatial
    # engineering, industrial/mining tech and the wider spatial-data ecosystem.
    ("lever", "RyzLabs", "RYZ Labs"),
    ("ashby", "squad", "Squad"),
    ("ashby", "g2i", "G2i"),
)


async def collect_targeted_companies(
    client: httpx.AsyncClient, *, now: datetime,
) -> tuple[list[Opportunity], dict[str, str]]:
    """Fetch a limited number of official job boards; errors stay per company."""
    limiter = asyncio.Semaphore(3)

    async def one(kind: str, token: str, company: str):
        async with limiter:
            key = f"{kind}:{token}"
            try:
                if kind == "ashby":
                    connector = AshbyConnector(client, board_name=token,
                                               company_name=company,
                                               timeout_seconds=14)
                elif kind == "lever":
                    connector = LeverConnector(client, site=token,
                                               company_name=company,
                                               timeout_seconds=14)
                else:
                    connector = GreenhouseConnector(client, board_token=token,
                                                    company_name=company,
                                                    timeout_seconds=14)
                found = await connector.fetch()
                return found, key, f"OK ({len(found)} parsed)"
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                return [], key, "ERROR:" + type(exc).__name__
            except Exception as exc:
                # Existing connectors use custom ConnectorError subclasses.
                return [], key, "ERROR:" + type(exc).__name__

    responses = await asyncio.gather(*(one(*row) for row in TARGET_BOARDS))
    jobs: list[Opportunity] = []
    diagnostics: dict[str, str] = {}
    for rows, key, status in responses:
        jobs.extend(rows)
        diagnostics[key] = status
    return jobs, diagnostics
