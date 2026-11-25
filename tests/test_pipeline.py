import hashlib
from zipfile import ZipFile

import pytest

from site_transfer import pipeline
from site_transfer.github import publish, review_kit


def test_kit_retry(tmp_path, monkeypatch):
    calls=[]
    def build(config, job, root, path):
        calls.append(path)
        if len(calls)==1:
            raise OSError("temporary")
        path.write_bytes(b"kit")
    monkeypatch.setattr(pipeline,"build_kit",build)
    result=pipeline.make_kit({}, {}, tmp_path,tmp_path/"kit.zip")
    assert result["attempts"]==2
    assert result["sha256"]==hashlib.sha256(b"kit").hexdigest()
    assert not list(tmp_path.glob("*.tmp"))


def test_no_retry_validation(tmp_path, monkeypatch):
    calls=[]
    def build(*args):
        calls.append(1)
        raise ValueError("invalid")
    monkeypatch.setattr(pipeline,"build_kit",build)
    with pytest.raises(ValueError):
        pipeline.make_kit({}, {}, tmp_path,tmp_path/"kit.zip")
    assert len(calls)==1


@pytest.fixture
def kit(tmp_path):
    path=tmp_path/"kit.zip"
    with ZipFile(path,"w") as archive:
        for name in ["CONTEXT.md","AGENTS.md","TASK.md","README.md","reference-kit.json"]:
            archive.writestr(name,"fixture")
    return path,hashlib.sha256(path.read_bytes()).hexdigest()


def test_review_required(kit):
    with pytest.raises(ValueError,match="approval"):
        publish(kit[0],"owner/repo",kit[1],request=lambda *a:pytest.fail("network"))


def test_digest_required(kit):
    with pytest.raises(ValueError,match="SHA256"):
        review_kit(kit[0],"0"*64)


def test_public_repo_denied(kit):
    with pytest.raises(ValueError,match="private"):
        publish(kit[0],"owner/repo",kit[1],True,request=lambda *a:{"private":False})


def test_reviewed_draft(kit):
    calls=[]
    def request(endpoint,method="GET",payload=None):
        calls.append((endpoint,method,payload))
        if endpoint=="/repos/owner/repo":
            return {"private":True,"default_branch":"main"}
        if "/git/ref/heads/" in endpoint:
            return {"object":{"sha":"abc"}}
        if endpoint.endswith("/pulls"):
            assert payload["draft"] is True
            return {"html_url":"https://github.com/owner/repo/pull/1"}
        return {}
    result=publish(kit[0],"owner/repo",kit[1],True,request=request)
    assert result["branch"].startswith("site-transfer/kit-")
    assert [c[1] for c in calls]==["GET","GET","POST","PUT","POST"]
    assert result["sha256"]==kit[1]
