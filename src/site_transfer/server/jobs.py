"""PostgreSQL owns job state, dispatch reservations and fencing."""
from uuid import uuid4

from psycopg.types.json import Jsonb
from .db import connect

from .settings import CAPTURE_LEASE
KIT_LEASE = 390      # Celery hard limit 330 + grace
DISPATCH_INTERVAL = 300
MAX_DISPATCH = 12
MAX_ATTEMPTS = 3


def create(job_id, project_id, pipeline=False):
    with connect() as conn:
        return conn.execute("""
            INSERT INTO capture_jobs (id, project_id, pipeline_enabled, kit_status)
            VALUES (%s,%s,%s,%s) RETURNING *
        """, (job_id,project_id,pipeline,"pending" if pipeline else "not_requested")).fetchone()


def get(project_id, job_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM capture_jobs WHERE project_id=%s AND id=%s",(project_id,job_id)).fetchone()


def list_jobs(project_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM capture_jobs WHERE project_id=%s ORDER BY created_at DESC,id DESC LIMIT 50",(project_id,)).fetchall()


def events(project_id,job_id):
    with connect() as conn:
        return conn.execute("""
            SELECT e.* FROM lifecycle_events e JOIN capture_jobs j ON j.id=e.job_id
            WHERE j.project_id=%s AND j.id=%s ORDER BY e.id DESC LIMIT 100
        """,(project_id,job_id)).fetchall()


def claim(job_id):
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET status='running', owner_token=%s, heartbeat_at=now(),
                lease_until=now()+%s*interval '1 second', updated_at=now()
            WHERE id=%s AND status='queued' AND NOT cancel_requested RETURNING *
        """,(uuid4(),CAPTURE_LEASE,job_id)).fetchone()


def progress(job_id, token, manifest):
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET manifest=%s,heartbeat_at=now(),updated_at=now()
            WHERE id=%s AND owner_token=%s AND status='running' AND lease_until>now()
            RETURNING id
        """,(Jsonb(manifest),job_id,token)).fetchone() is not None


def cancelled(job_id,token):
    with connect() as conn:
        return conn.execute("""
            SELECT id FROM capture_jobs WHERE id=%s AND owner_token=%s AND status='running'
              AND NOT cancel_requested AND lease_until>now()
        """,(job_id,token)).fetchone() is None


def finish(job_id,token,status,error=None):
    if status not in ("completed","partial","failed"):
        raise ValueError("Invalid terminal status")
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET
                status=CASE WHEN cancel_requested THEN 'failed' ELSE %s END,
                error=CASE WHEN cancel_requested THEN 'Cancelled; recorded evidence preserved' ELSE %s END,
                kit_status=CASE WHEN cancel_requested AND pipeline_enabled THEN 'cancelled'
                    WHEN pipeline_enabled AND %s='failed' THEN 'failed' ELSE kit_status END,
                owner_token=NULL,lease_until=NULL,updated_at=now(),dispatch_after=now(),dispatch_attempts=0
            WHERE id=%s AND owner_token=%s AND status='running' AND lease_until>now()
            RETURNING *
        """,(status,error,status,job_id,token)).fetchone()


def request_cancel(project_id,job_id):
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET cancel_requested=true,
                status=CASE WHEN status='queued' THEN 'failed' ELSE status END,
                error=CASE WHEN status='queued' THEN 'Cancelled before start' ELSE error END,
                kit_status=CASE WHEN kit_status='pending' THEN 'cancelled' ELSE kit_status END,
                updated_at=now()
            WHERE project_id=%s AND id=%s AND NOT cancel_requested
              AND (status IN ('queued','running') OR
                   (status IN ('completed','partial') AND kit_status IN ('pending','building')))
            RETURNING *
        """,(project_id,job_id)).fetchone()


def retry_capture(project_id,job_id):
    # The original row and filesystem root are never reused. Unique parent prevents forks.
    with connect() as conn:
        previous=conn.execute("""
            SELECT * FROM capture_jobs WHERE project_id=%s AND id=%s FOR UPDATE
        """,(project_id,job_id)).fetchone()
        if previous is None or previous["status"]!="failed" or previous["attempt"]>=MAX_ATTEMPTS:
            return None
        existing=conn.execute("SELECT * FROM capture_jobs WHERE retry_of=%s",(job_id,)).fetchone()
        if existing is not None:
            return existing
        return conn.execute("""
            INSERT INTO capture_jobs(id,project_id,pipeline_enabled,kit_status,attempt,retry_of)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING *
        """,(uuid4(),project_id,previous["pipeline_enabled"],
             "pending" if previous["pipeline_enabled"] else "not_requested",
             previous["attempt"]+1,job_id)).fetchone()


def request_kit(project_id,job_id):
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET kit_status='pending',kit_info='{}',dispatch_attempts=0,
                dispatch_after=now(),updated_at=now()
            WHERE project_id=%s AND id=%s AND status IN ('completed','partial')
                AND kit_status IN ('not_requested','failed') AND NOT cancel_requested
                AND kit_attempt<%s RETURNING *
        """,(project_id,job_id,MAX_ATTEMPTS)).fetchone()


def claim_kit(project_id,job_id):
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET kit_status='building',kit_attempt=kit_attempt+1,
                owner_token=%s,lease_until=now()+%s*interval '1 second',
                heartbeat_at=now(),updated_at=now()
            WHERE project_id=%s AND id=%s AND status IN ('completed','partial')
                AND kit_status='pending' AND NOT cancel_requested AND kit_attempt<%s RETURNING *
        """,(uuid4(),KIT_LEASE,project_id,job_id,MAX_ATTEMPTS)).fetchone()


def finish_kit(job_id,token,status,info):
    if status not in ("ready","failed"):
        raise ValueError("Invalid kit status")
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET kit_status=CASE WHEN cancel_requested THEN 'cancelled' ELSE %s END,
                kit_info=CASE WHEN cancel_requested THEN '{}'::jsonb ELSE %s END,
                owner_token=NULL,lease_until=NULL,updated_at=now()
            WHERE id=%s AND owner_token=%s AND kit_status='building' AND lease_until>now()
            RETURNING *
        """,(status,Jsonb(info),job_id,token)).fetchone()


def worker_heartbeat(name):
    with connect() as conn:
        conn.execute("""
            INSERT INTO worker_heartbeat(name,seen_at) VALUES(%s,now())
            ON CONFLICT(name) DO UPDATE SET seen_at=excluded.seen_at
        """,(name,))


def worker_ready():
    with connect() as conn:
        return conn.execute("SELECT 1 FROM worker_heartbeat WHERE seen_at>now()-interval '90 seconds' LIMIT 1").fetchone() is not None


def reconcile(limit=20):
    """Retire expired owners, retry expired kit attempts only; never overwrite capture roots."""
    with connect() as conn:
        rows=conn.execute("""
            SELECT id FROM capture_jobs WHERE
            ((status='running' OR kit_status='building') AND lease_until<=now())
            OR ((status='queued' OR (status IN ('completed','partial') AND kit_status='pending'))
                AND dispatch_attempts >= %s AND dispatch_after<=now())
            ORDER BY updated_at LIMIT %s FOR UPDATE SKIP LOCKED
        """,(MAX_DISPATCH,limit)).fetchall()
        for row in rows:
            conn.execute("""
                UPDATE capture_jobs SET
                    status=CASE WHEN status IN ('running','queued') THEN 'failed' ELSE status END,
                    error=CASE WHEN status='running' THEN 'Capture lease expired; retry as new run'
                               WHEN status='queued' THEN 'Dispatch budget exhausted; retry as new run' ELSE error END,
                    kit_status=CASE
                        WHEN cancel_requested AND kit_status IN ('pending','building') THEN 'cancelled'
                        WHEN status IN ('running','queued') AND pipeline_enabled THEN 'failed'
                        WHEN kit_status='building' AND kit_attempt<%s THEN 'pending'
                        WHEN kit_status IN ('pending','building') THEN 'failed' ELSE kit_status END,
                    kit_info=CASE WHEN kit_status IN ('pending','building')
                        THEN '{"error":"Recovered interrupted or undispatched stage"}'::jsonb ELSE kit_info END,
                    owner_token=NULL,lease_until=NULL,dispatch_after=now(),dispatch_attempts=0,updated_at=now()
                WHERE id=%s
            """,(MAX_ATTEMPTS,row["id"]))
        return len(rows)


def reserve_dispatch(limit=10):
    """Commit bounded reservation before broker send; duplicate delivery is harmless."""
    with connect() as conn:
        return conn.execute("""
            WITH due AS (
                SELECT id FROM capture_jobs
                WHERE NOT cancel_requested AND dispatch_after<=now() AND dispatch_attempts<%s
                  AND (status='queued' OR (status IN ('completed','partial') AND kit_status='pending' AND kit_attempt<%s))
                ORDER BY dispatch_after,id LIMIT %s FOR UPDATE SKIP LOCKED
            )
            UPDATE capture_jobs j SET dispatch_attempts=j.dispatch_attempts+1,
                dispatch_after=now()+%s*interval '1 second',updated_at=now()
            FROM due WHERE j.id=due.id
            RETURNING j.id,j.project_id,j.status,j.dispatch_attempts
        """,(MAX_DISPATCH,MAX_ATTEMPTS,limit,DISPATCH_INTERVAL)).fetchall()
