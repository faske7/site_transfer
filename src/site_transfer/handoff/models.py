"""Immutable input contracts for the offline handoff engine.

Capture state, evidence integrity and eventual requirement confidence are
independent. A checksum calculated during export is not a capture-time proof.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, TypeAlias, Union


class CaptureStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"


class EvidenceKind(str, Enum):
    CAPTURE_MANIFEST = "capture_manifest"
    ROUTES = "routes"
    SCREENSHOT = "screenshot"
    DESIGN_REPORT = "design_report"
    DESIGN_TOKENS = "design_tokens"
    ASSET_MANIFEST = "asset_manifest"
    INTERACTION_MANIFEST = "interaction_manifest"
    INTERACTION_SCREENSHOT = "interaction_screenshot"
    DEVICE_MANIFEST = "device_manifest"
    DEVICE_SCREENSHOT = "device_screenshot"
    TIMELINE_MANIFEST = "timeline_manifest"
    TIMELINE_IMAGE = "timeline_image"


class HashProvenance(str, Enum):
    RECORDED = "capture_recorded"
    COMPUTED = "computed_at_load"


JsonValue: TypeAlias = Union[
    None, bool, int, float, str,
    tuple["JsonValue", ...], Mapping[str, "JsonValue"],
]


@dataclass(frozen=True, slots=True)
class EvidenceFile:
    id: str
    path: str  # relative to the future kit root, never a local absolute path
    kind: EvidenceKind
    size_bytes: int
    sha256: str
    hash_provenance: HashProvenance


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    json_pointer: str | None = None  # RFC 6901; resolved in a later stage


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    run_id: str
    status: CaptureStatus
    files: Mapping[str, EvidenceFile]
    documents: Mapping[str, JsonValue]

    def document(self, path: str) -> JsonValue:
        """Lookup by the exact kit-relative path; never reads the filesystem."""
        return self.documents[path]
