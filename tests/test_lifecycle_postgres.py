"""Opt-in real PostgreSQL tests. Never use production DSN."""
import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

psycopg=pytest.importorskip("psycopg")
from psycopg import sql
from psycopg.rows import dict_row

from site_transfer.server import db,jobs

DSN=os.getenv("SITE_TRANSFER_TEST_POSTGRES_DSN")
pytestmark=pytest.mark.skipif(not DSN,reason="Set disposable PostgreSQL test DSN")


@pytest.fixture
def registry(monkeypatch):
    schema="test_lifecycle_"+uuid4().hex
    with psycopg.connect(DSN,autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(DSN,row_factory=dict_row,options="-c search_path="+schema)
    monkeypatch.setattr(db,"connect",connect)
    monkeypatch.setattr(jobs,"connect",connect)
    try:
        db.migrate()
        db.migrate()  # idempotent migration
        project=uuid4()
        db.create_project(project,{"source":{"url":"https://example.com"},"target":{"project_name":"fixture"}})
        yield project,connect
    finally:
        with psycopg.connect(DSN,autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def expire(connect,job):
    with connect() as conn:
        conn.execute("UPDATE capture_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(job,))


def completed(project):
    job=uuid4()
    jobs.create(job,project,True)
    owner=jobs.claim(job)
    assert jobs.finish(job,owner["owner_token"],"completed")
    return job


def test_duplicate_capture_claim(registry):
    project,_=registry
    job=uuid4()
    jobs.create(job,project)
    barrier=Barrier(2)
    def claim():
        barrier.wait(timeout=5)
        return jobs.claim(job)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:claim(),range(2)))
    assert sum(x is not None for x in results)==1


def test_stale_capture_fencing_and_new_run(registry):
    project,connect=registry
    job=uuid4()
    jobs.create(job,project,True)
    owner=jobs.claim(job)["owner_token"]
    evidence={"artifacts":[{"path":"screenshots/desktop/a.png"}]}
    assert jobs.progress(job,owner,evidence)
    expire(connect,job)
    assert jobs.reconcile()==1
    assert jobs.get(project,job)["status"]=="failed"
    assert jobs.get(project,job)["manifest"]==evidence
    assert not jobs.progress(job,owner,{})
    assert jobs.finish(job,owner,"completed") is None
    retry=jobs.retry_capture(project,job)
    assert retry["id"]!=job and retry["attempt"]==2 and retry["retry_of"]==job
    assert jobs.retry_capture(project,job)["id"]==retry["id"]
    assert jobs.get(project,job)["manifest"]==evidence
    assert jobs.events(project,job)[0]["status"]=="failed"


def test_capture_retry_budget(registry):
    project,_=registry
    job=uuid4()
    jobs.create(job,project)
    for expected in (1,2,3):
        current=jobs.claim(job)
        assert current["attempt"]==expected
        assert jobs.finish(job,current["owner_token"],"failed")
        retry=jobs.retry_capture(project,job)
        if expected==3:
            assert retry is None
        else:
            job=retry["id"]


def test_cancel_before_capture_claim(registry):
    project,_=registry
    job=uuid4()
    jobs.create(job,project,True)
    assert jobs.request_cancel(project,job)["status"]=="failed"
    assert jobs.claim(job) is None
    assert jobs.reserve_dispatch()==[]
    assert jobs.request_cancel(project,job) is None


def test_cancel_wins_before_finish(registry):
    project,_=registry
    job=uuid4()
    jobs.create(job,project,True)
    token=jobs.claim(job)["owner_token"]
    assert jobs.request_cancel(project,job)
    assert jobs.cancelled(job,token)
    result=jobs.finish(job,token,"completed")
    assert result["status"]=="failed" and result["kit_status"]=="cancelled"
    assert jobs.claim_kit(project,job) is None


def test_finish_wins_before_cancel_without_kit(registry):
    project,_=registry
    job=uuid4()
    jobs.create(job,project)
    token=jobs.claim(job)["owner_token"]
    assert jobs.finish(job,token,"completed")
    assert jobs.request_cancel(project,job) is None


def test_lost_dispatch_reservation_and_exhaustion(registry):
    project,connect=registry
    job=uuid4()
    jobs.create(job,project)
    assert jobs.reserve_dispatch()[0]["dispatch_attempts"]==1
    assert jobs.reserve_dispatch()==[]
    with connect() as conn:
        conn.execute("UPDATE capture_jobs SET dispatch_after=now()-interval '1 second' WHERE id=%s",(job,))
    assert jobs.reserve_dispatch()[0]["dispatch_attempts"]==2
    with connect() as conn:
        conn.execute("UPDATE capture_jobs SET dispatch_attempts=%s,dispatch_after=now()-interval '1 second' WHERE id=%s",
                     (jobs.MAX_DISPATCH,job))
    assert jobs.reconcile()==1
    assert jobs.get(project,job)["status"]=="failed"
    assert jobs.claim(job) is None


def test_expired_kit_retries_and_fences_old_writer(registry):
    project,connect=registry
    job=completed(project)
    old=jobs.claim_kit(project,job)
    assert jobs.claim_kit(project,job) is None
    expire(connect,job)
    assert jobs.reconcile()==1
    assert jobs.get(project,job)["kit_status"]=="pending"
    new=jobs.claim_kit(project,job)
    assert new["kit_attempt"]==2 and new["owner_token"]!=old["owner_token"]
    assert jobs.finish_kit(job,old["owner_token"],"ready",{"sha256":"old"}) is None
    result=jobs.finish_kit(job,new["owner_token"],"ready",{"sha256":"new"})
    assert result["kit_info"]=={"sha256":"new"}
    assert jobs.request_kit(project,job) is None


def test_kit_exhaustion(registry):
    project,connect=registry
    job=completed(project)
    for expected in (1,2,3):
        assert jobs.claim_kit(project,job)["kit_attempt"]==expected
        expire(connect,job)
        assert jobs.reconcile()==1
    assert jobs.get(project,job)["kit_status"]=="failed"
    assert jobs.request_kit(project,job) is None


def test_cancel_kit_cannot_publish(registry):
    project,_=registry
    job=completed(project)
    token=jobs.claim_kit(project,job)["owner_token"]
    assert jobs.request_cancel(project,job)
    result=jobs.finish_kit(job,token,"ready",{"sha256":"cancelled"})
    assert result["kit_status"]=="cancelled" and result["kit_info"]=={}
    assert result["status"]=="completed"


def test_worker_heartbeat_and_event_scope(registry):
    project,connect=registry
    assert not jobs.worker_ready()
    jobs.worker_heartbeat("worker-test")
    assert jobs.worker_ready()
    with connect() as conn:
        conn.execute("UPDATE worker_heartbeat SET seen_at=now()-interval '91 seconds'")
    assert not jobs.worker_ready()
    job=uuid4()
    jobs.create(job,project)
    assert len(jobs.events(project,job))==1
    assert jobs.events(uuid4(),job)==[]
