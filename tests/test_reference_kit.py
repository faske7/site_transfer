import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from site_transfer.assets import safe_source, inventory, combine
from site_transfer.manifest import build_kit, evidence_file


def test_source_redaction():
    assert safe_source("https://example.com/image.png?token=secret#x") == "https://example.com/image.png"
    assert safe_source("https://user:password@example.com/x") is None
    assert safe_source("data:image/png;base64,secret") is None


def test_inventory_no_source_bytes():
    class Page:
        def evaluate(self, js):
            return {"items":[{"kind":"image","url":"https://example.com/a.png?q=1","detail":""}]*2,"truncated":False}
    report = inventory(Page(), "https://example.com/", "desktop")
    result = combine([report, report])
    assert result["count"] == 1
    assert result["items"][0]["sha256"] is None
    assert result["items"][0]["downloaded"] is False
    assert result["items"][0]["license"] == "unknown"


@pytest.fixture
def kit(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    path = root / "screenshots" / "desktop" / "a.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture screenshot")
    manifest = {"artifacts":[{"path":"screenshots/desktop/a.png","sha256":hashlib.sha256(path.read_bytes()).hexdigest()}],
                "errors":[]}
    (root / "routes.json").write_text("[]")
    (root / "capture-manifest.json").write_text(json.dumps(manifest))
    config = json.loads((Path(__file__).resolve().parents[1] / "examples/remaxdelux.json").read_text())
    job = {"id":"fixture-run","status":"completed","manifest":manifest}
    return root, config, job, tmp_path / "kit.zip"


def test_selected_kit(kit):
    root, config, job, output = kit
    (root / "unlisted.txt").write_text("not exported")
    index = build_kit(config, job, root, output)
    with ZipFile(output) as archive:
        assert {"CONTEXT.md","AGENTS.md","TASK.md","README.md","reference-kit.json"}.issubset(archive.namelist())
        assert "design/reference/screenshots/desktop/a.png" in archive.namelist()
        assert not any("unlisted" in n for n in archive.namelist())
        assert len(index["files"]) == 3


def test_active_run_rejected(kit):
    root, config, job, output = kit
    job["status"] = "running"
    with pytest.raises(ValueError):
        build_kit(config, job, root, output)


def test_checksum_mismatch(kit):
    root, config, job, output = kit
    (root / "screenshots/desktop/a.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        build_kit(config, job, root, output)


@pytest.mark.parametrize("name", ["../secret", "/etc/passwd", "screenshots/../../secret"])
def test_traversal(kit, name):
    with pytest.raises(ValueError):
        evidence_file(kit[0], name)


def test_symlink_rejected(kit):
    root = kit[0]
    (root / "alias.png").symlink_to(root / "screenshots/desktop/a.png")
    with pytest.raises(ValueError):
        evidence_file(root, "alias.png")
