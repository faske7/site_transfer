"""Bounded durable dispatch and reconciliation, driven by the API lifespan."""
import logging
from contextlib import asynccontextmanager
from threading import Event, Thread
from uuid import uuid4

from . import jobs
from .worker import run_capture, run_kit

log=logging.getLogger(__name__)


def tick():
    jobs.reconcile()
    if not jobs.worker_ready():
        return
    for row in jobs.reserve_dispatch():
        try:
            if row["status"]=="queued":
                run_capture.apply_async(args=[str(row["id"])],task_id=str(uuid4()),retry=False)
            else:
                run_kit.apply_async(args=[str(row["project_id"]),str(row["id"])],task_id=str(uuid4()),retry=False)
        except Exception:
            # Reservation survives a lost/ambiguous broker response; the next due
            # reservation may resend, and claim() fences duplicates.
            log.warning("Dispatch attempt failed for %s",row["id"])


def loop(stop):
    while not stop.is_set():
        try:
            tick()
        except Exception:
            log.exception("Lifecycle reconciliation failed")
        stop.wait(5)


@asynccontextmanager
async def lifespan(app):
    stop=Event()
    thread=Thread(target=loop,args=(stop,),name="lifecycle-recovery",daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)
