"""Resolve only recorded screenshot paths within a specific job."""
from pathlib import Path
from uuid import UUID

from .settings import project_root


def run_root(project_id: UUID, job_id: UUID):
    return project_root() / str(project_id) / "design" / "reference" / "runs" / str(job_id)


def screenshot_path(project_id, job_id, manifest, index):
    entries = (manifest or {}).get("artifacts", [])
    if index < 0 or index >= len(entries):
        raise FileNotFoundError
    root = run_root(project_id, job_id).resolve()
    path = (root / entries[index]["path"]).resolve()
    if not path.is_relative_to(root / "screenshots") or path.suffix != ".png" or not path.is_file():
        raise FileNotFoundError
    return path


def append_capture_context(project_id, job_id, status, count):
    # Existing projects keep their user-edited context. The per-run manifest is authoritative.
    path = project_root() / str(project_id) / "CONTEXT.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n- Capture run {job_id}: {status}, {count} screenshots. See design/reference/runs/{job_id}/capture-manifest.json.\n")
