import hashlib
import json

import pytest

from site_transfer.handoff import load_evidence
from site_transfer.handoff.models import CaptureStatus, EvidenceKind, HashProvenance
from site_transfer.manifest import verify_selected_evidence


def write_json(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    name = "screenshots/desktop/a.png"
    image = root / name
    image.parent.mkdir(parents=True)
    image.write_bytes(b"opaque screenshot fixture")
    routes = ["https://example.com/"]
    manifest = {
        "routes": routes,
        "artifacts": [{"path": name, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}],
        "errors": [],
        "design_reports": [{"path": "design/a.json"}],
    }
    write_json(root, "routes.json", routes)
    write_json(root, "capture-manifest.json", manifest)
    write_json(root, "design/a.json", {"elements": [{"style": {"gap": "12px"}}]})
    return root, {"id": "run-one", "status": "completed", "manifest": manifest}


def test_load_selected_only_and_provenance(run):
    root, job = run
    write_json(root, "asset-manifest.json", {"unlisted": True})
    bundle = load_evidence(job, root)
    assert bundle.status == CaptureStatus.COMPLETED
    assert len(bundle.files) == 4
    prefix = "design/reference/"
    image = bundle.files[prefix + "screenshots/desktop/a.png"]
    assert image.kind == EvidenceKind.SCREENSHOT
    assert image.hash_provenance == HashProvenance.RECORDED
    assert bundle.files[prefix + "design/a.json"].hash_provenance == HashProvenance.COMPUTED
    assert prefix + "asset-manifest.json" not in bundle.files
    assert image.path not in bundle.documents
    assert bundle.document(prefix + "routes.json") == ("https://example.com/",)


def test_stable_ids_and_run_isolation(run):
    root, job = run
    first = load_evidence(job, root)
    second = load_evidence(job, root)
    other = load_evidence(dict(job, id="run-two"), root)
    assert first == second
    assert {f.id for f in first.files.values()}.isdisjoint(f.id for f in other.files.values())
    assert list(first.files) == sorted(first.files)


def test_immutable_nested_json(run):
    root, job = run
    bundle = load_evidence(job, root)
    with pytest.raises(TypeError):
        bundle.document("design/reference/design/a.json")["elements"][0]["style"]["gap"] = "0px"
    with pytest.raises(TypeError):
        bundle.files["new"] = None
    job["manifest"]["routes"].append("https://example.com/other")
    assert bundle.document("design/reference/routes.json") == ("https://example.com/",)


def test_partial_legacy_run(run):
    root, job = run
    job["status"] = "partial"
    job["manifest"].pop("routes")
    job["manifest"].pop("design_reports")
    write_json(root, "capture-manifest.json", job["manifest"])
    bundle = load_evidence(job, root)
    assert bundle.status == CaptureStatus.PARTIAL
    assert len(bundle.files) == 3


@pytest.mark.parametrize("status", ["running", "failed", "cancelled"])
def test_nonexportable_status(run, status):
    root, job = run
    with pytest.raises(ValueError, match="completed or partial"):
        load_evidence(dict(job, status=status), root)


def test_no_screenshots(run):
    root, job = run
    job["manifest"]["artifacts"] = []
    with pytest.raises(ValueError, match="No screenshots"):
        load_evidence(job, root)


def test_image_tampering(run):
    root, job = run
    (root / "screenshots/desktop/a.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        load_evidence(job, root)


def test_missing_recorded_report(run):
    root, job = run
    (root / "design/a.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        load_evidence(job, root)


def test_registry_mismatch(run):
    root, job = run
    write_json(root, "capture-manifest.json", {})
    with pytest.raises(ValueError, match="differs from registry"):
        load_evidence(job, root)


def test_routes_mismatch(run):
    root, job = run
    write_json(root, "routes.json", ["https://example.com/other"])
    with pytest.raises(ValueError, match="Routes evidence differs"):
        load_evidence(job, root)


@pytest.mark.parametrize("value", ["{", "[]", '{"number": NaN}'])
def test_invalid_design_report(run, value):
    root, job = run
    (root / "design/a.json").write_text(value)
    with pytest.raises(ValueError):
        load_evidence(job, root)


def test_symlink_rejected(run, tmp_path):
    root, job = run
    target = tmp_path / "other.json"
    target.write_text("{}")
    (root / "design/a.json").unlink()
    (root / "design/a.json").symlink_to(target)
    with pytest.raises(ValueError, match="Symbolic links"):
        load_evidence(job, root)


def test_traversal_rejected(run):
    root, job = run
    job["manifest"]["design_reports"][0]["path"] = "design/../../other.json"
    write_json(root, "capture-manifest.json", job["manifest"])
    with pytest.raises(ValueError, match="Invalid artifact path"):
        load_evidence(job, root)


def test_shared_verifier_preserves_legacy_export_contract(run):
    root, job = run
    # The legacy ZIP verifier does not interpret unrelated design report JSON.
    (root / "design/a.json").write_text("not JSON")
    entries, reports, selected = verify_selected_evidence(job, root)
    assert len(entries) == 4
    assert reports["capture-manifest.json"] == job["manifest"]
    assert selected["design/a.json"] is None
    with pytest.raises(ValueError):
        load_evidence(job, root)


def test_size_limit(run, monkeypatch):
    root, job = run
    monkeypatch.setattr("site_transfer.manifest.MAX_BYTES", 1)
    with pytest.raises(ValueError, match="512 MiB"):
        load_evidence(job, root)
