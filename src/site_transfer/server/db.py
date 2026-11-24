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
        return conn.execute("SELECT version FROM studio_schema WHERE version = 1").fetchone() is not None
