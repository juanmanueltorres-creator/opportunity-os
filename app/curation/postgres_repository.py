"""PostgreSQL-backed curation ledger; no SQLite dependency."""
from __future__ import annotations
import json
import os
from app.curation.models import CurationRunRecord, PublicationCheckpoint

def _connect():
    dsn=os.getenv("OPPORTUNITY_POSTGRES_WRITE_DSN")
    if not dsn:raise RuntimeError("PostgreSQL writer required; no SQLite fallback")
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(dsn,connect_timeout=8,sslmode="require",row_factory=dict_row)

class PostgresCurationLedgerRepository:
    def initialize(self):
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select 1 from opportunity_os.curation_runs limit 0")

    def record_run(self,record:CurationRunRecord,*,payload_json:str):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select payload_sha256 from opportunity_os.curation_runs where run_id=%s for update",(record.run_id,))
            row=cur.fetchone()
            if row:return "IDENTICAL" if row["payload_sha256"]==record.payload_sha256 else "CONFLICT"
            cur.execute("""insert into opportunity_os.curation_runs
                (run_id,generated_at,recorded_at,payload_sha256,digest_id,payload_json)
                values(%s,%s,%s,%s,%s,%s) on conflict(run_id) do nothing returning run_id""",
                (record.run_id,record.generated_at,record.recorded_at,
                 record.payload_sha256,record.digest_id,payload_json))
            return "NEW" if cur.fetchone() else "CONFLICT"

    def get_run_record(self,run_id):
        raw=self.get_run_payload_json(run_id)
        return CurationRunRecord.model_validate(json.loads(raw)["record"]) if raw else None

    def get_run_payload_json(self,run_id):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select payload_json from opportunity_os.curation_runs where run_id=%s",(run_id,))
            row=cur.fetchone()
        return row["payload_json"] if row else None

    def list_run_payload_json(self,*,limit):
        if not 1<=limit<=100:raise ValueError("limit must be within 1..100")
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("""select payload_json from opportunity_os.curation_runs
                order by generated_at desc,run_id desc limit %s""",(limit,))
            return [r["payload_json"] for r in cur.fetchall()]

    def list_publication_checkpoints_for_run(self,run_id):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("""select payload_json from opportunity_os.publication_checkpoints
                where run_id=%s order by confirmed_at,checkpoint_id""",(run_id,))
            return [PublicationCheckpoint.model_validate_json(r["payload_json"]) for r in cur.fetchall()]

    def publication_count(self):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select count(*) as n from opportunity_os.publication_checkpoints")
            return cur.fetchone()["n"]

    def record_publication_if_count_unchanged(self,checkpoint,*,expected_publication_count):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("curation:publication-counter",))
            cur.execute("select count(*) as n from opportunity_os.publication_checkpoints")
            if cur.fetchone()["n"]!=expected_publication_count:return False
            cur.execute("""insert into opportunity_os.publication_checkpoints
                (checkpoint_id,run_id,digest_id,channel,confirmed_by,confirmed_at,preview_sha256,payload_json)
                values(%s,%s,%s,%s,%s,%s,%s,%s)""",
                (checkpoint.checkpoint_id,checkpoint.run_id,checkpoint.digest_id,
                 checkpoint.channel,checkpoint.confirmed_by,checkpoint.confirmed_at,
                 checkpoint.preview_sha256,checkpoint.model_dump_json()))
            for oid in checkpoint.opportunity_ids:
                cur.execute("""insert into opportunity_os.publication_checkpoint_items
                    (checkpoint_id,opportunity_id,confirmed_at) values(%s,%s,%s)""",
                    (checkpoint.checkpoint_id,oid,checkpoint.confirmed_at))
            return True

    def list_recently_published_opportunity_ids(self,*,since,until):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("""select distinct opportunity_id from opportunity_os.publication_checkpoint_items
                where confirmed_at between %s and %s order by opportunity_id""",(since,until))
            return {r["opportunity_id"] for r in cur.fetchall()}

    def get_publication_by_preview_sha256(self,preview_sha256):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("""select payload_json from opportunity_os.publication_checkpoints
              where preview_sha256=%s order by confirmed_at,checkpoint_id limit 1""",(preview_sha256,))
            row=cur.fetchone()
        return PublicationCheckpoint.model_validate_json(row["payload_json"]) if row else None

    def list_published_opportunity_ids_for_run(self,*,run_id,opportunity_ids):
        if not opportunity_ids:return set()
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("""select distinct i.opportunity_id from opportunity_os.publication_checkpoint_items i
                join opportunity_os.publication_checkpoints c on c.checkpoint_id=i.checkpoint_id
                where c.run_id=%s and i.opportunity_id=any(%s)""",(run_id,opportunity_ids))
            return {r["opportunity_id"] for r in cur.fetchall()}

    def list_published_opportunity_ids(self,opportunity_ids):
        if not opportunity_ids:return set()
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("""select distinct opportunity_id from opportunity_os.publication_checkpoint_items
              where opportunity_id=any(%s)""",(opportunity_ids,))
            return {r["opportunity_id"] for r in cur.fetchall()}
