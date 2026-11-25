"""Durable capture-job state; PostgreSQL owns transitions."""
from psycopg.types.json import Jsonb

from .db import connect


def create(job_id, project_id, pipeline=False):
    with connect() as conn:
        return conn.execute("""
            INSERT INTO capture_jobs (id, project_id, pipeline_enabled, kit_status) VALUES (%s, %s, %s, %s)
            RETURNING *
        """, (job_id, project_id, pipeline, "pending" if pipeline else "not_requested")).fetchone()


def get(project_id, job_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM capture_jobs WHERE project_id=%s AND id=%s", (project_id, job_id)).fetchone()


def list_jobs(project_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM capture_jobs WHERE project_id=%s ORDER BY created_at DESC, id DESC LIMIT 50", (project_id,)).fetchall()


def claim(job_id):
    with connect() as conn:
        return conn.execute("UPDATE capture_jobs SET status='running', updated_at=now() WHERE id=%s AND status='queued' RETURNING *", (job_id,)).fetchone()


def progress(job_id, manifest):
    with connect() as conn:
        conn.execute("UPDATE capture_jobs SET manifest=%s, updated_at=now() WHERE id=%s AND status='running'", (Jsonb(manifest), job_id))


def finish(job_id, status, error=None, expected="running"):
    with connect() as conn:
        conn.execute("UPDATE capture_jobs SET status=%s, error=%s, updated_at=now() WHERE id=%s AND status=%s", (status, error, job_id, expected))


def request_cancel(project_id, job_id):
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET cancel_requested=true,
                status=CASE WHEN status='queued' THEN 'failed' ELSE status END,
                error=CASE WHEN status='queued' THEN 'Cancelled before start' ELSE error END,
                kit_status=CASE WHEN status='queued' AND pipeline_enabled THEN 'cancelled' ELSE kit_status END,
                updated_at=now()
            WHERE project_id=%s AND id=%s AND status IN ('queued','running') RETURNING *
        """,(project_id,job_id)).fetchone()


def cancelled(job_id):
    with connect() as conn:
        row=conn.execute("SELECT cancel_requested FROM capture_jobs WHERE id=%s",(job_id,)).fetchone()
        return row is None or row["cancel_requested"]


def claim_kit(project_id, job_id):
    with connect() as conn:
        return conn.execute("""
            UPDATE capture_jobs SET kit_status='building', updated_at=now()
            WHERE project_id=%s AND id=%s AND status IN ('completed','partial')
              AND kit_status IN ('pending','failed','not_requested') AND NOT cancel_requested
            RETURNING *
        """,(project_id,job_id)).fetchone()


def finish_kit(job_id, status, info):
    with connect() as conn:
        conn.execute("UPDATE capture_jobs SET kit_status=%s,kit_info=%s,updated_at=now() WHERE id=%s AND kit_status='building'",
                     (status,Jsonb(info),job_id))
