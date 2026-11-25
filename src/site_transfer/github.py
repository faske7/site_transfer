"""Host-only explicit review publication using the authenticated gh CLI."""
import base64
import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from .manifest import digest

MAX_UPLOAD = 20 * 1024 * 1024
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")


def gh_api(endpoint, method="GET", payload=None):
    command = ["gh", "api", "--hostname", "github.com", "--method", method, endpoint]
    if payload is not None:
        command.extend(["--input", "-"])
    try:
        result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                                text=True, capture_output=True, timeout=120, check=True)
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        # Do not expose credential-bearing subprocess output.
        raise ValueError("GitHub operation failed; inspect gh auth status and remote branch before retry") from exc


def review_kit(path, expected):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_UPLOAD:
        raise ValueError("Choose a regular ZIP of at most 20 MiB")
    if not re.fullmatch(r"[a-f0-9]{64}", expected) or digest(path) != expected:
        raise ValueError("Reviewed ZIP SHA256 does not match")
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not {"CONTEXT.md","AGENTS.md","TASK.md","README.md","reference-kit.json"}.issubset(names):
            raise ValueError("Expected a generated Reference Kit")
        if sum(x.file_size for x in archive.infolist()) > 513*1024*1024:
            raise ValueError("ZIP exceeds expanded size limit")
    data = path.read_bytes()
    import hashlib
    if len(data) > MAX_UPLOAD or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("ZIP changed after review")
    return data


def publish(path, repository, expected, approved=False, request=gh_api):
    if not approved:
        raise ValueError("Explicit review approval required")
    if not REPO.fullmatch(repository) or repository.split("/")[1] in (".", ".."):
        raise ValueError("Use owner/repository")
    data = review_kit(path, expected)
    repo = request("/repos/"+repository)
    if not repo.get("private") or repo.get("archived"):
        raise ValueError("Publication is limited to active private repositories")
    from urllib.parse import quote
    base = repo["default_branch"]
    head = request("/repos/"+repository+"/git/ref/heads/"+quote(base,safe=""))["object"]["sha"]
    branch = "site-transfer/kit-"+expected[:12]+"-"+uuid4().hex[:8]
    request("/repos/"+repository+"/git/refs","POST",{"ref":"refs/heads/"+branch,"sha":head})
    try:
        request("/repos/"+repository+"/contents/site-transfer/reference-kit-"+expected[:12]+".zip","PUT",
                {"message":"Add reviewed Site Transfer reference kit","content":base64.b64encode(data).decode("ascii"),"branch":branch})
        result = request("/repos/"+repository+"/pulls","POST",{"title":"Review Site Transfer reference kit",
                         "body":"Reviewed ZIP SHA256: "+expected+"\nExtract into a separate directory and read CONTEXT.md and TASK.md. Review rights before reuse.",
                         "head":branch,"base":base,"draft":True})
    except Exception as exc:
        raise ValueError("Publication may be incomplete; inspect branch "+branch+" before retry") from exc
    return {"branch":branch,"pull_request":result["html_url"],"sha256":expected}
