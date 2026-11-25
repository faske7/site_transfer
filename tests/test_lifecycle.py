"""Fast fault-injection tests; database transitions have separate integration coverage."""
from uuid import uuid4

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("celery")

from site_transfer.server import recovery, worker


def test_dispatch_pauses_without_worker(monkeypatch):
    calls=[]
    monkeypatch.setattr(recovery.jobs,"reconcile",lambda:calls.append("reconcile"))
    monkeypatch.setattr(recovery.jobs,"worker_ready",lambda:False)
    monkeypatch.setattr(recovery.jobs,"reserve_dispatch",lambda:pytest.fail("No live worker"))
    recovery.tick()
    assert calls==["reconcile"]


def test_ambiguous_dispatch_does_not_drop_following_intent(monkeypatch):
    capture,kit,project=uuid4(),uuid4(),uuid4()
    monkeypatch.setattr(recovery.jobs,"reconcile",lambda:0)
    monkeypatch.setattr(recovery.jobs,"worker_ready",lambda:True)
    monkeypatch.setattr(recovery.jobs,"reserve_dispatch",lambda:[
        {"id":capture,"project_id":project,"status":"queued"},
        {"id":kit,"project_id":project,"status":"completed"},
    ])
    sent=[]
    def fail(**kwargs):
        sent.append(kwargs["args"])
        raise OSError("Broker response lost")
    monkeypatch.setattr(recovery.run_capture,"apply_async",fail)
    monkeypatch.setattr(recovery.run_kit,"apply_async",lambda **kwargs:sent.append(kwargs["args"]))
    recovery.tick()
    assert sent==[[str(capture)],[str(project),str(kit)]]


def test_duplicate_delivery_no_browser(monkeypatch):
    monkeypatch.setattr(worker.jobs,"claim",lambda _:None)
    monkeypatch.setattr(worker,"capture_site",lambda *a:pytest.fail("Duplicate task navigated"))
    worker.run_capture.run(str(uuid4()))


def test_fenced_capture_does_not_append_context(monkeypatch,tmp_path):
    job,project,token=uuid4(),uuid4(),uuid4()
    monkeypatch.setattr(worker.jobs,"claim",lambda _:{"project_id":project,"owner_token":token})
    monkeypatch.setattr(worker.db,"get_project",lambda _:{"config":{}})
    monkeypatch.setattr(worker,"run_root",lambda *_:tmp_path)
    monkeypatch.setattr(worker.jobs,"progress",lambda *_:False)
    def capture(config,root,progress,cancelled):
        progress({"artifacts":[]})
        pytest.fail("Lost ownership must interrupt capture")
    monkeypatch.setattr(worker,"capture_site",capture)
    monkeypatch.setattr(worker.jobs,"finish",lambda *_:None)
    monkeypatch.setattr(worker,"append_capture_context",lambda *_:pytest.fail("Fenced owner wrote context"))
    worker.run_capture.run(str(job))


def test_kit_attempt_path_is_owner_scoped(monkeypatch,tmp_path):
    project,job,token=uuid4(),uuid4(),uuid4()
    monkeypatch.setattr(worker.jobs,"claim_kit",lambda *_:{"owner_token":token})
    monkeypatch.setattr(worker.db,"get_project",lambda _:{"config":{}})
    monkeypatch.setattr(worker,"run_root",lambda *_:tmp_path)
    seen=[]
    def build(config,record,root,path):
        assert path==tmp_path/"kits"/(str(token)+".zip")
        return {"sha256":"abc"}
    monkeypatch.setattr(worker,"make_kit",build)
    monkeypatch.setattr(worker.jobs,"finish_kit",lambda *args:seen.append(args))
    worker.run_kit.run(str(project),str(job))
    assert seen==[(job,token,"ready",{"sha256":"abc","path":"kits/"+str(token)+".zip"})]
