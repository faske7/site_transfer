"""Versioned PostgreSQL schema and project registry."""
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .settings import database_options


def connect():
    return psycopg.connect(**database_options(), row_factory=dict_row)


def migrate():
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(73102001)")
        conn.execute("CREATE TABLE IF NOT EXISTS studio_schema (version integer PRIMARY KEY)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id uuid PRIMARY KEY,
                config jsonb NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        conn.execute("INSERT INTO studio_schema (version) VALUES (1) ON CONFLICT DO NOTHING")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capture_jobs (
                id uuid PRIMARY KEY,
                project_id uuid NOT NULL REFERENCES projects(id),
                status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','partial','failed')),
                manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
                error text,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS capture_active_project ON capture_jobs(project_id) WHERE status IN ('queued','running')")
        conn.execute("INSERT INTO studio_schema (version) VALUES (2) ON CONFLICT DO NOTHING")
        conn.execute("ALTER TABLE capture_jobs ADD COLUMN IF NOT EXISTS pipeline_enabled boolean NOT NULL DEFAULT false")
        conn.execute("ALTER TABLE capture_jobs ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT false")
        conn.execute("ALTER TABLE capture_jobs ADD COLUMN IF NOT EXISTS kit_status text NOT NULL DEFAULT 'not_requested'")
        conn.execute("ALTER TABLE capture_jobs ADD COLUMN IF NOT EXISTS kit_info jsonb NOT NULL DEFAULT '{}'::jsonb")
        conn.execute("INSERT INTO studio_schema (version) VALUES (3) ON CONFLICT DO NOTHING")
        if not conn.execute("SELECT version FROM studio_schema WHERE version=4").fetchone():
            from .lifecycle_schema import upgrade
            upgrade(conn)
            conn.execute("INSERT INTO studio_schema (version) VALUES (4)")


def create_project(project_id: UUID, config: dict) -> dict:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO projects (id, config) VALUES (%s, %s) RETURNING id, config, created_at",
            (project_id, Jsonb(config)),
        ).fetchone()


def get_project(project_id: UUID) -> dict | None:
    with connect() as conn:
        return conn.execute("SELECT id, config, created_at FROM projects WHERE id = %s", (project_id,)).fetchone()


def list_projects(limit: int, offset: int) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, config, created_at FROM projects ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()


def ready() -> bool:
    with connect() as conn:
        return conn.execute("SELECT version FROM studio_schema WHERE version = 4").fetchone() is not None
