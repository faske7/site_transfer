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


def append_capture_context(project_id, job_id, status, count, design_count=0):
    # Existing projects keep their user-edited context. The per-run manifest is authoritative.
    path = project_root() / str(project_id) / "CONTEXT.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n- Capture run {job_id}: {status}, {count} screenshots, {design_count} design reports. See design/reference/runs/{job_id}/capture-manifest.json.\n")


def design_path(project_id, job_id, manifest, index=None):
    root = run_root(project_id, job_id).resolve()
    manifest = manifest or {}
    if index is None:
        if manifest.get("design_tokens") != "design-tokens.json":
            raise FileNotFoundError
        path = (root / "design-tokens.json").resolve()
        if path.parent != root:
            raise FileNotFoundError
    else:
        entries = manifest.get("design_reports", [])
        if index < 0 or index >= len(entries):
            raise FileNotFoundError
        path = (root / entries[index]["path"]).resolve()
        if not path.is_relative_to(root / "design"):
            raise FileNotFoundError
    if path.suffix != ".json" or not path.is_file():
        raise FileNotFoundError
    return path
