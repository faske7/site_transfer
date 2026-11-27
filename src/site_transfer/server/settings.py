"""Runtime configuration. Credentials are passed separately to psycopg."""
import os
from pathlib import Path

# One source of truth for the task budget and registry fencing deadline.
CAPTURE_SOFT_TIMEOUT = 90 * 60
CAPTURE_HARD_TIMEOUT = CAPTURE_SOFT_TIMEOUT + 30
CAPTURE_LEASE = CAPTURE_HARD_TIMEOUT + 120


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
