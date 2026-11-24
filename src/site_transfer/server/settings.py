"""Runtime configuration. Credentials are passed separately to psycopg."""
import os
from pathlib import Path


def database_options() -> dict:
    return {
        "host": os.environ.get("POSTGRES_HOST", "db"),
        "dbname": os.environ.get("POSTGRES_DB", "site_transfer"),
        "user": os.environ.get("POSTGRES_USER", "studio"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "connect_timeout": 3,
    }


def redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://redis:6379/0")


def project_root() -> Path:
    return Path(os.environ.get("PROJECT_ROOT", "/data/projects"))
