"""Worker runtime only; capture tasks arrive in PR-04."""
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
