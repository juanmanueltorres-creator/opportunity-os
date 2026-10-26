"""Private PostgreSQL relationship repository with transactional event projection.

Keeps the existing SQLite runtime unchanged until the final backend cutover.
"""
from __future__ import annotations
from collections.abc import Callable

from app.relationships.models import CareerContact, RelationshipAccount, RelationshipEvent
from app.repositories.postgres import _connect


class PostgresRelationshipRepository:
    def initialize(self):
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select 1 from opportunity_os.relationship_events limit 0")

    @staticmethod
    def _account(cur, account_id):
        cur.execute("select payload_json from opportunity_os.relationship_accounts where account_id=%s", (account_id,))
        row=cur.fetchone()
        return RelationshipAccount.model_validate_json(row["payload_json"]) if row else None

    @staticmethod
    def _contact(cur, contact_id):
        cur.execute("select payload_json from opportunity_os.relationship_contacts where contact_id=%s", (contact_id,))
        row=cur.fetchone()
        return CareerContact.model_validate_json(row["payload_json"]) if row else None

    @staticmethod
    def _contacts(cur, account_id):
        cur.execute("select payload_json from opportunity_os.relationship_contacts where account_id=%s order by contact_id", (account_id,))
        return [CareerContact.model_validate_json(r["payload_json"]) for r in cur.fetchall()]

    @staticmethod
    def _event(cur, event_id):
        cur.execute("select payload_json from opportunity_os.relationship_events where event_id=%s", (event_id,))
        row=cur.fetchone()
        return RelationshipEvent.model_validate_json(row["payload_json"]) if row else None

    def get_account(self, account_id):
        with _connect() as conn,conn.cursor() as cur:return self._account(cur,account_id)

    def list_accounts(self):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select payload_json from opportunity_os.relationship_accounts order by account_id")
            return [RelationshipAccount.model_validate_json(r["payload_json"]) for r in cur.fetchall()]

    def get_contact(self, contact_id):
        with _connect() as conn,conn.cursor() as cur:return self._contact(cur,contact_id)

    def list_contacts(self, account_id):
        with _connect() as conn,conn.cursor() as cur:return self._contacts(cur,account_id)

    def get_event(self,event_id):
        with _connect() as conn,conn.cursor() as cur:return self._event(cur,event_id)

    def list_events(self,account_id):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select payload_json from opportunity_os.relationship_events where account_id=%s order by occurred_at,event_id",(account_id,))
            return [RelationshipEvent.model_validate_json(r["payload_json"]) for r in cur.fetchall()]

    @staticmethod
    def _validate(cur,event):
        existing=PostgresRelationshipRepository._event(cur,event.event_id)
        if existing is not None:
            if existing!=event:raise ValueError("relationship event_id conflict")
            return "IDENTICAL"
        cur.execute("""select occurred_at,event_id from opportunity_os.relationship_events
             where account_id=%s order by occurred_at desc,event_id desc limit 1""",(event.account_id,))
        last=cur.fetchone()
        if last and (event.occurred_at,event.event_id)<=(last["occurred_at"],last["event_id"]):
            raise ValueError("out-of-order relationship event")
        return "NEW"

    def validate_event(self,event):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("relation:"+event.account_id,))
            return self._validate(cur,event)

    @classmethod
    def _save_contact(cls,cur,contact):
        cur.execute("""insert into opportunity_os.relationship_contacts
            (contact_id,account_id,disposition,verification_status,payload_json,updated_at)
            values(%s,%s,%s,%s,%s,%s) on conflict(contact_id) do update set
            account_id=excluded.account_id,disposition=excluded.disposition,
            verification_status=excluded.verification_status,payload_json=excluded.payload_json,
            updated_at=excluded.updated_at""",(contact.contact_id,contact.account_id,contact.disposition,
            contact.verification_status,contact.model_dump_json(),contact.observed_at))

    @classmethod
    def _save_account(cls,cur,account):
        if account.preferred_next_contact_id:
            contact=cls._contact(cur,account.preferred_next_contact_id)
            if not contact or contact.account_id!=account.account_id or not contact.active or contact.disposition!="AVAILABLE":
                raise ValueError("preferred contact must belong to account and be active/available")
        cur.execute("""insert into opportunity_os.relationship_accounts
          (account_id,relationship_state,last_contacted_at,cooldown_until,open_process,payload_json,updated_at)
          values(%s,%s,%s,%s,%s,%s,%s) on conflict(account_id) do update set
          relationship_state=excluded.relationship_state,last_contacted_at=excluded.last_contacted_at,
          cooldown_until=excluded.cooldown_until,open_process=excluded.open_process,
          payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
          (account.account_id,account.relationship_state,account.last_contacted_at,
           account.cooldown_until,account.open_process,account.model_dump_json(),account.updated_at))

    def save_account(self,account):
        with _connect() as conn,conn.cursor() as cur:self._save_account(cur,account)
        return account

    def save_contact(self,contact):
        with _connect() as conn,conn.cursor() as cur:self._save_contact(cur,contact)
        return contact

    def append_event(self,event):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("relation:"+event.account_id,))
            if self._validate(cur,event)=="IDENTICAL":return event
            self._insert(cur,event)
        return event

    @staticmethod
    def _insert(cur,event):
        cur.execute("""insert into opportunity_os.relationship_events
          (event_id,account_id,contact_id,kind,payload_json,occurred_at)
          values(%s,%s,%s,%s,%s,%s)""",
          (event.event_id,event.account_id,event.contact_id,event.kind,event.model_dump_json(),event.occurred_at))

    def apply_event_transaction(self,event,projector):
        with _connect() as conn,conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("relation:"+event.account_id,))
            disposition=self._validate(cur,event)
            if disposition=="IDENTICAL":
                account=self._account(cur,event.account_id)
                if account is None:raise ValueError("idempotent event has no relationship account projection")
                return event,account
            account=self._account(cur,event.account_id)
            contacts=self._contacts(cur,event.account_id)
            next_account,next_contacts=projector(account,contacts)
            if next_account.account_id!=event.account_id:raise ValueError("projection account_id mismatch")
            for contact in next_contacts:
                if contact.account_id!=event.account_id:raise ValueError("projection contact account_id mismatch")
            self._insert(cur,event)
            for contact in next_contacts:self._save_contact(cur,contact)
            self._save_account(cur,next_account)
            return event,next_account
