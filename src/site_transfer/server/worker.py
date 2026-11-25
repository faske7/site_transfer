"""Celery runners; the registry fences all terminal writes."""
import logging
from time import monotonic
from uuid import UUID

from celery import Celery, signals
from celery.exceptions import SoftTimeLimitExceeded
from site_transfer.capture import capture_site
from site_transfer.pipeline import CaptureCancelled, make_kit
from . import db, jobs
from .storage import run_root, append_capture_context
from .settings import redis_url

log = logging.getLogger(__name__)
app = Celery("site_transfer", broker=redis_url())
app.conf.update(
    task_serializer="json", accept_content=["json"], task_ignore_result=True,
    broker_connection_retry_on_startup=True, worker_prefetch_multiplier=1,
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout":3,"socket_timeout":3},
)
_last_heartbeat = 0.0


@signals.heartbeat_sent.connect
def record_worker_heartbeat(sender=None, **kwargs):
    # Runs in the worker's parent, including while a prefork child is busy.
    global _last_heartbeat
    now=monotonic()
    if now-_last_heartbeat<15:
        return
    _last_heartbeat=now
    try:
        jobs.worker_heartbeat(str(getattr(getattr(sender,"eventer",None),"hostname","studio-worker")))
    except Exception:
        log.warning("Worker registry heartbeat failed")


@app.task(name="studio.capture", soft_time_limit=1800, time_limit=1830)
def run_capture(job_id):
    job_id=UUID(job_id)
    job=jobs.claim(job_id)
    if job is None:
        return
    project_id,token=job["project_id"],job["owner_token"]
    status,error,count,design_count="failed",None,0,0
    try:
        config=db.get_project(project_id)["config"]
        def update(manifest):
            nonlocal count,design_count
            if not jobs.progress(job_id,token,manifest):
                raise CaptureCancelled("Capture ownership lost")
            count=len(manifest["artifacts"])
            design_count=len(manifest.get("design_reports",[]))
        result=capture_site(config,run_root(project_id,job_id),update,
                            lambda: jobs.cancelled(job_id,token))
        status="completed" if count and not result["errors"] else "partial" if count else "failed"
        if not count:
            error="No screenshots captured"
    except CaptureCancelled:
        error="Capture interrupted; recorded evidence preserved"
    except SoftTimeLimitExceeded:
        error="Capture exceeded 30 minute job limit"
    except Exception:
        error="Capture failed; inspect recorded evidence"
        log.exception("Capture failed: %s",job_id)
    finished=jobs.finish(job_id,token,status,error)
    if finished is None:
        return
    # Registry is authoritative. Context is an auxiliary append after ownership is committed.
    try:
        append_capture_context(project_id,job_id,finished["status"],count,design_count)
    except OSError:
        log.warning("Context update failed for %s",job_id)
    # Dispatcher handles the independent kit task after capture commits.


@app.task(name="studio.kit", soft_time_limit=300, time_limit=330)
def run_kit(project_id,job_id):
    project_id,job_id=UUID(project_id),UUID(job_id)
    job=jobs.claim_kit(project_id,job_id)
    if job is None:
        return
    token=job["owner_token"]
    root=run_root(project_id,job_id)
    # Never overwrite a previous or concurrent owner's output. Only the fenced row
    # can publish an attempt path; abandoned files stay unreferenced for recovery.
    name="kits/"+str(token)+".zip"
    try:
        info=make_kit(db.get_project(project_id)["config"],job,root,root/name)
        info["path"]=name
    except Exception:
        jobs.finish_kit(job_id,token,"failed",{"error":"Kit build failed; retry from saved capture"})
    else:
        jobs.finish_kit(job_id,token,"ready",info)
