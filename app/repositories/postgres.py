"""PostgreSQL repository contracts for the Opportunity OS radar.

These do not alter legacy SQLite startup. Use a dedicated writer connection
with the opportunity_os_writer role and the private schema migrations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
import os

from app.models.domain import Opportunity
from app.availability.models import AvailabilityObservation, OpportunityAvailability
from app.availability.repository import _project
from app.radar.models import OpportunityEnrichment
from app.repositories.enrichments import _canonical_taxonomy_versions

def _connect():
    dsn=os.getenv("OPPORTUNITY_POSTGRES_WRITE_DSN")
    if not dsn:
        raise RuntimeError("OPPORTUNITY_POSTGRES_WRITE_DSN is required; no SQLite fallback")
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(dsn,connect_timeout=8,sslmode="require",row_factory=dict_row)

def _record(row):
    # PostgreSQL has richer non-domain metadata than the strict Opportunity model.
    return Opportunity.model_validate({k:row[k] for k in
      ("id","source","source_id","source_url","company","title","description",
       "discovered_at","status","location","remote_policy","published_at",
       "required_skills","preferred_skills","compensation")})

def _dedupe(job):
    return "|".join(" ".join((x or "").casefold().split()) for x in
                    (job.company,job.title,job.location))

class PostgresOpportunityRepository:
    def initialize(self):
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1 from opportunity_os.opportunities limit 0")

    def upsert(self, job:Opportunity)->tuple[Opportunity,bool]:
        # Lock by normalized identity to prevent simultaneous cross-source duplicates.
        key=_dedupe(job)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))",(key,))
                cur.execute("""select * from opportunity_os.opportunities
                    where (source=%s and source_id=%s) or dedupe_key=%s
                    order by discovered_at,id limit 1 for update""",
                    (job.source,job.source_id,key))
                existing=cur.fetchone()
                if existing:
                    return _record(existing),False
                cur.execute("""insert into opportunity_os.opportunities
                  (id,source,source_id,source_url,company,title,description,discovered_at,
                   status,location,remote_policy,published_at,required_skills,preferred_skills,
                   compensation,dedupe_key)
                  values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                  returning *""",
                  (job.id,job.source,job.source_id,job.source_url,job.company,job.title,
                   job.description,job.discovered_at,job.status,job.location,job.remote_policy,
                   job.published_at,job.required_skills,job.preferred_skills,job.compensation,key))
                return _record(cur.fetchone()),True

    def get(self,opportunity_id:str)->Opportunity|None:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select * from opportunity_os.opportunities where id=%s",(opportunity_id,))
                row=cur.fetchone()
        return _record(row) if row else None

    def list(self,limit:int=100)->list[Opportunity]:
        if limit<1:return []
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""select * from opportunity_os.opportunities
                   order by discovered_at desc,id asc limit %s""",(limit,))
                rows=cur.fetchall()
        return [_record(r) for r in rows]

    def list_radar_candidates(self,*,now:datetime,lookback_days:int)->list[Opportunity]:
        if now.tzinfo is None or now.utcoffset() is None:raise ValueError("now must be timezone-aware")
        if lookback_days<0:raise ValueError("lookback_days must be non-negative")
        cutoff=now.astimezone(timezone.utc)-timedelta(days=lookback_days)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""select * from opportunity_os.opportunities
                  where coalesce(published_at,discovered_at) between %s and %s
                  order by coalesce(published_at,discovered_at) desc,id asc""",
                  (cutoff,now.astimezone(timezone.utc)))
                rows=cur.fetchall()
        return [_record(r) for r in rows]

class PostgresAvailabilityRepository:
    def initialize(self):
        with _connect() as conn:
            with conn.cursor() as cur:cur.execute("select 1 from opportunity_os.availability_observations limit 0")

    def record(self,item:AvailabilityObservation):
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""insert into opportunity_os.availability_observations
                  (opportunity_id,observation_type,observed_at,evidence_source,source_url,note,
                   evidence_kind,confirmed_by,confirmed_at,preview_sha256)
                  values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (item.opportunity_id,item.observation_type,item.observed_at,item.evidence_source,
                   item.source_url,item.note,item.evidence_kind,item.confirmed_by,item.confirmed_at,item.preview_sha256))

    def record_seen(self,opportunity_id:str,*,observed_at:datetime,evidence_source:str,source_url:str|None=None):
        self.record(AvailabilityObservation(opportunity_id=opportunity_id,observation_type="SEEN",
            observed_at=observed_at,evidence_source=evidence_source,source_url=source_url))

    def record_verification(self,opportunity_id:str,*,is_open:bool,observed_at:datetime,
                            evidence_source:str,source_url:str|None=None,note:str|None=None):
        # Schema requires human confirmation for a verified status: never synthesize one.
        raise ValueError("Use record(AvailabilityObservation) with explicit confirmed_by and evidence URL")

    def list_observations(self,opportunity_id:str)->list[AvailabilityObservation]:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""select opportunity_id,observation_type,observed_at,
                  evidence_source,source_url,note,evidence_kind,confirmed_by,confirmed_at,preview_sha256
                  from opportunity_os.availability_observations where opportunity_id=%s
                  order by observed_at,id""",(opportunity_id,))
                rows=cur.fetchall()
        return [AvailabilityObservation.model_validate(r) for r in rows]

    def get(self,opportunity_id:str)->OpportunityAvailability|None:
        obs=self.list_observations(opportunity_id)
        return _project(opportunity_id,obs) if obs else None

    def get_many(self,opportunity_ids:list[str])->dict[str,OpportunityAvailability]:
        return {i:v for i in dict.fromkeys(opportunity_ids) if (v:=self.get(i)) is not None}

    def record_if_unchanged(self,item:AvailabilityObservation,*,
                            expected_observation_count:int,expected_latest_observation_at:datetime|None)->bool:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))",("availability:"+item.opportunity_id,))
                cur.execute("""select count(*) as n,max(observed_at) as latest
                  from opportunity_os.availability_observations where opportunity_id=%s""",(item.opportunity_id,))
                row=cur.fetchone()
                if row["n"]!=expected_observation_count or row["latest"]!=expected_latest_observation_at:
                    return False
                cur.execute("""insert into opportunity_os.availability_observations
                  (opportunity_id,observation_type,observed_at,evidence_source,source_url,note,
                   evidence_kind,confirmed_by,confirmed_at,preview_sha256)
                  values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (item.opportunity_id,item.observation_type,item.observed_at,item.evidence_source,
                   item.source_url,item.note,item.evidence_kind,item.confirmed_by,item.confirmed_at,item.preview_sha256))
                return True

class PostgresEnrichmentRepository:
    def initialize(self):
        with _connect() as conn:
            with conn.cursor() as cur:cur.execute("select 1 from opportunity_os.opportunity_enrichments limit 0")

    def save(self,enrichment:OpportunityEnrichment,*,extractor_version:str,
             alias_registry_version:str,taxonomy_versions:dict[str,str])->None:
        extractor=extractor_version.strip();alias=alias_registry_version.strip()
        if not extractor or not alias:raise ValueError("enrichment versions must be non-empty")
        if extractor!=enrichment.extractor_version:raise ValueError("extractor version mismatch")
        if taxonomy_versions!=enrichment.taxonomy_versions:raise ValueError("taxonomy versions mismatch")
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""insert into opportunity_os.opportunity_enrichments
                 (opportunity_id,extractor_version,alias_registry_version,taxonomy_versions_json,payload_json)
                 values(%s,%s,%s,%s,%s)
                 on conflict(opportunity_id,extractor_version,alias_registry_version,taxonomy_versions_json)
                 do update set payload_json=excluded.payload_json""",
                 (enrichment.opportunity_id,extractor,alias,
                  _canonical_taxonomy_versions(taxonomy_versions),enrichment.model_dump_json()))

    def get_current(self,opportunity_id:str,version_tuple:tuple[str,str,dict[str,str]])->OpportunityEnrichment|None:
        a,b,c=version_tuple
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""select payload_json from opportunity_os.opportunity_enrichments
                 where opportunity_id=%s and extractor_version=%s and alias_registry_version=%s
                 and taxonomy_versions_json=%s limit 1""",
                 (opportunity_id,a.strip(),b.strip(),_canonical_taxonomy_versions(c)))
                row=cur.fetchone()
        return OpportunityEnrichment.model_validate_json(row["payload_json"]) if row else None
