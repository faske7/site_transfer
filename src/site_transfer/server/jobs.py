"""Durable capture-job state; PostgreSQL owns transitions."""
from psycopg.types.json import Jsonb

from .db import connect


def create(job_id, project_id):
    with connect() as conn:
        return conn.execute("""
            INSERT INTO capture_jobs (id, project_id) VALUES (%s, %s)
            RETURNING *
        """, (job_id, project_id)).fetchone()


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
