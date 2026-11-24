"""Celery capture runner."""
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded
from site_transfer.capture import capture_site
from . import db, jobs
from .storage import run_root, append_capture_context
from celery import Celery

from .settings import redis_url

app = Celery("site_transfer", broker=redis_url())
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
)


@app.task(name="studio.capture", soft_time_limit=1800, time_limit=1830)
def run_capture(job_id):
    job_id = UUID(job_id)
    job = jobs.claim(job_id)
    if job is None:
        return
    project_id = job["project_id"]
    status, error, count = "failed", None, 0
    try:
        config = db.get_project(project_id)["config"]
        def update(manifest):
            nonlocal count
            count = len(manifest["artifacts"])
            jobs.progress(job_id, manifest)
        result = capture_site(config, run_root(project_id, job_id), update)
        status = "completed" if count and not result["errors"] else "partial" if count else "failed"
        if not count:
            error = "No screenshots captured"
    except SoftTimeLimitExceeded:
        error = "Capture exceeded 30 minute job limit"
    except Exception as exc:
        error = str(exc)[:500]
    try:
        append_capture_context(project_id, job_id, status, count)
    except OSError:
        status = "partial" if count else "failed"
        error = "Could not update CONTEXT.md"
    jobs.finish(job_id, status, error)
