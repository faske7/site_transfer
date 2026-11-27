"""Read selected terminal capture evidence without network or browser work."""
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType

from ..manifest import PREFIX, read_verified_json, verify_selected_evidence
from .models import (
    CaptureStatus, EvidenceBundle, EvidenceFile, EvidenceKind, HashProvenance,
    JsonValue,
)


_FIXED_KINDS = {
    "capture-manifest.json": EvidenceKind.CAPTURE_MANIFEST,
    "routes.json": EvidenceKind.ROUTES,
    "design-tokens.json": EvidenceKind.DESIGN_TOKENS,
    "asset-manifest.json": EvidenceKind.ASSET_MANIFEST,
    "interaction-manifest.json": EvidenceKind.INTERACTION_MANIFEST,
    "device-manifest.json": EvidenceKind.DEVICE_MANIFEST,
    "scroll-timeline-manifest.json": EvidenceKind.TIMELINE_MANIFEST,
}


def _kind(name: str) -> EvidenceKind:
    if name in _FIXED_KINDS:
        return _FIXED_KINDS[name]
    for prefix, kind in (
        ("screenshots/", EvidenceKind.SCREENSHOT),
        ("design/", EvidenceKind.DESIGN_REPORT),
        ("interactions/", EvidenceKind.INTERACTION_SCREENSHOT),
        ("devices/", EvidenceKind.DEVICE_SCREENSHOT),
    ):
        if name.startswith(prefix):
            return kind
    # Remaining names originate only from the shared timeline allowlist,
    # including frame, difference, panorama and storyboard images.
    if name.endswith(".png"):
        return EvidenceKind.TIMELINE_IMAGE
    raise ValueError("Unsupported selected evidence kind")


def _freeze(value) -> JsonValue:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON evidence value")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError("Unsupported JSON evidence value")


def _id(run_id: str, path: str) -> str:
    # Unambiguous encoding; stable for the same run and kit-relative path.
    identity = json.dumps([run_id, path], ensure_ascii=True, separators=(",", ":"))
    return "EV-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def load_evidence(job: dict, root: Path | str) -> EvidenceBundle:
    """Load an immutable snapshot of the selected run's JSON and file metadata.

    Reuse kit integrity checks. Optional unrecorded files are ignored, not
    discovered. Missing recorded files or malformed JSON fail closed. Legacy
    records may lack route metadata, reports, quality or capture-time hashes.
    PNG bytes are streamed for integrity only, never decoded or retained.
    The caller supplies the trusted registry job and its corresponding run root.
    """
    entries, reports, selected = verify_selected_evidence(job, root)
    run_id = str(job["id"])
    if not run_id:
        raise ValueError("Missing capture run identity")
    files = {}
    documents = {}
    for name, source, size, checksum in sorted(entries, key=lambda entry: entry[0]):
        path = PREFIX + name
        kind = _kind(name)
        files[path] = EvidenceFile(
            id=_id(run_id, path), path=path, kind=kind, size_bytes=size,
            sha256=checksum,
            hash_provenance=(
                HashProvenance.RECORDED if selected[name] else HashProvenance.COMPUTED
            ),
        )
        if name.endswith(".json"):
            report = reports[name] if name in reports else read_verified_json(source, checksum)
            if kind == EvidenceKind.ROUTES:
                if not isinstance(report, list) or not all(isinstance(url, str) for url in report):
                    raise ValueError("Invalid routes evidence")
                if "routes" in job["manifest"] and report != job["manifest"]["routes"]:
                    raise ValueError("Routes evidence differs from registry")
            elif not isinstance(report, dict):
                raise ValueError("Expected object in JSON evidence: " + name)
            documents[path] = _freeze(report)
    return EvidenceBundle(
        run_id=run_id, status=CaptureStatus(job["status"]),
        files=MappingProxyType(files), documents=MappingProxyType(documents),
    )
