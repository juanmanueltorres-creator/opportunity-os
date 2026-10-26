"""Postgres-only private writes, conservative evidence, and one known-source refresh."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Annotated, Literal

import httpx
from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.connectors.remotive import RemotiveConnector
from app.models.domain import Opportunity
from app.postgres_read_api import Auth, _authorize, app

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ManualVacancy(Strict):
    source: str = Field(min_length=1, max_length=90)
    source_url: str = Field(min_length=8, max_length=2048)
    source_id: str = Field(min_length=1, max_length=250)
    company: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    location: str | None = None
    published_at: datetime | None = None
    remote_policy: str | None = None
    @field_validator("published_at")
    @classmethod
    def aware(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timezone required")
        return value

class ApplicationInput(Strict):
    company: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    status: Literal["DRAFT","SENT","APPLIED","REPLIED","INTERVIEW","REJECTED","WITHDRAWN","UNKNOWN"]
    event_at: datetime
    source_reference: str = Field(min_length=8)
    notes: str | None = None
    @field_validator("event_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone required")
        return value

class VerificationInput(Strict):
    observation_type: Literal["VERIFIED_OPEN","VERIFIED_CLOSED"]
    source_url: str = Field(min_length=8)
    evidence_source: str = Field(min_length=1)
    confirmed_by: str = Field(min_length=1)
    note: str | None = None

def _write(sql: str, params: tuple[object, ...], *, returning: bool = True):
    dsn = os.getenv("OPPORTUNITY_POSTGRES_WRITE_DSN", "")
    if not dsn:
        raise HTTPException(503, "PostgreSQL writer not configured")
    try:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(dsn, connect_timeout=8, sslmode="require", row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                value = cursor.fetchone() if returning else None
            connection.commit()
            return value
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Postgres write failed: %s", type(exc).__name__)
        raise HTTPException(503, "PostgreSQL write unavailable") from exc

def _vacancy_hash(source: str, source_id: str):
    return hashlib.sha256((source+"\0"+source_id).encode()).hexdigest()[:24]

def _dedupe(company: str, title: str, location: str | None):
    return "|".join(" ".join((part or "").casefold().split()) for part in (company,title,location))

def _store_vacancy(job: Opportunity):
    return _write("""
    insert into opportunity_os.opportunities
      (id,source,source_id,source_url,company,title,description,location,remote_policy,
       remote_mode,published_at,discovered_at,last_seen_at,status,dedupe_key,
       required_skills,preferred_skills,compensation)
    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    on conflict (source,source_id) do update
      set last_seen_at=excluded.last_seen_at,updated_at=now()
    returning id, (xmax=0) as created
    """,(job.id,job.source,job.source_id,job.source_url,job.company,job.title,
         job.description,job.location,job.remote_policy,
         "REMOTE" if (job.remote_policy or "").lower()=="remote" else "UNKNOWN",
         job.published_at,job.discovered_at,job.discovered_at,job.status,
         _dedupe(job.company,job.title,job.location),job.required_skills,
         job.preferred_skills,job.compensation))

@app.post("/api/v1/opportunities/manual", dependencies=[Auth])
def add_manual_vacancy(payload: ManualVacancy):
    if not payload.source_url.startswith("https://"):
        raise HTTPException(422,"HTTPS source URL required")
    now=datetime.now(timezone.utc)
    job=Opportunity(id=f"{payload.source}:{_vacancy_hash(payload.source,payload.source_id)}",
        source=payload.source,source_id=payload.source_id,source_url=payload.source_url,
        company=payload.company,title=payload.title,description=payload.description,
        discovered_at=now,location=payload.location,remote_policy=payload.remote_policy,
        published_at=payload.published_at)
    return _store_vacancy(job)

@app.post("/api/v1/history/applications", dependencies=[Auth])
def save_application(payload: ApplicationInput):
    key="api-"+hashlib.sha256((payload.source_reference+"\0"+payload.company+"\0"+payload.role_title).encode()).hexdigest()[:32]
    return _write("""
       insert into opportunity_os.applications
       (application_key,company,role_title,channel,status,event_at,source_reference,notes)
       values(%s,%s,%s,%s,%s,%s,%s,%s)
       on conflict(application_key) do nothing
       returning application_key
    """,(key,payload.company,payload.role_title,payload.channel,payload.status,
         payload.event_at,payload.source_reference,payload.notes)) or {"application_key":key,"existing":True}

@app.post("/api/v1/opportunities/{opportunity_id}/verify", dependencies=[Auth])
def verify_vacancy(opportunity_id: str, payload: VerificationInput):
    if not payload.source_url.startswith("https://"):
        raise HTTPException(422,"HTTPS evidence URL required")
    return _write("""
    with target as (
      select id from opportunity_os.opportunities where id=%s
    ), recorded as (
      insert into opportunity_os.availability_observations
        (opportunity_id,observation_type,observed_at,evidence_source,source_url,note,confirmed_by)
      select id,%s,now(),%s,%s,%s,%s from target
      returning opportunity_id, observed_at
    )
    update opportunity_os.opportunities o
       set verification_status=case when %s='VERIFIED_OPEN' then 'VERIFIED' else 'REJECTED' end,
           last_verified_at=recorded.observed_at,updated_at=now()
    from recorded where o.id=recorded.opportunity_id
    returning o.id,o.verification_status,o.last_verified_at
    """,(opportunity_id,payload.observation_type,payload.evidence_source,
         payload.source_url,payload.note,payload.confirmed_by,payload.observation_type)) or {"status":"not_found"}

@app.get("/api/v1/opportunities/{opportunity_id}/observations",dependencies=[Auth])
def observations(opportunity_id: str):
    from app.postgres_read_api import _select
    return _select("""select observation_type,observed_at,evidence_source,source_url,note,
    confirmed_by from opportunity_os.availability_observations
    where opportunity_id=%s order by observed_at desc,id desc limit 100""",(opportunity_id,))

class RefreshRequest(Strict):
    source: Literal["remotive"]

@app.post("/api/v1/source/refresh",dependencies=[Auth])
async def refresh_one_source(request: RefreshRequest):
    """Fetch only the real existing Remotive connector; never promote to VERIFIED."""
    async with httpx.AsyncClient(follow_redirects=False) as client:
        jobs=await RemotiveConnector(client,timeout_seconds=12).fetch()
    # Cap each refresh, with unverified availability by default.
    created=existing=0
    for job in jobs[:250]:
        result=_store_vacancy(job)
        if result and result["created"]: created+=1
        else: existing+=1
    return {"source":"remotive","fetched":len(jobs),"processed":created+existing,
            "created":created,"existing":existing,"verification":"PENDING"}
