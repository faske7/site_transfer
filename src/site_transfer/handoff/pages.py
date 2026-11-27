"""Route inventory using only selected, immutable capture records."""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from urllib.parse import urlsplit

from .models import EvidenceBundle, EvidenceKind, EvidenceRef

PREFIX = "design/reference/"


def stable_id(prefix, *parts):
    payload = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return prefix + "-" + hashlib.sha256(payload.encode()).hexdigest()


def rows(value):
    return value if isinstance(value, tuple) else ()


def obj(value):
    return value if isinstance(value, Mapping) else {}


def ref(bundle, name, pointer=None, kind=None):
    file = bundle.files.get(PREFIX + name) if isinstance(name, str) else None
    if file is None or (kind is not None and file.kind != kind):
        return None
    return EvidenceRef(file.id, pointer)


@dataclass(frozen=True, slots=True)
class PageEvidence:
    kind: str
    viewport: str | None
    status: str
    quality: str
    record: EvidenceRef
    artifact: EvidenceRef | None


@dataclass(frozen=True, slots=True)
class Page:
    id: str
    url: str
    route: str
    route_ref: EvidenceRef
    evidence: tuple[PageEvidence, ...]
    limitations: tuple[str, ...]


def quality(row):
    value = obj(row.get("quality")).get("status")
    return value if value in ("valid", "warning", "invalid") else "unknown"


def build_page_map(bundle: EvidenceBundle) -> tuple[Page, ...]:
    manifest = bundle.document(PREFIX + "capture-manifest.json")
    routes = bundle.document(PREFIX + "routes.json")
    index = {url: [] for url in routes}
    for key, kind, artifact_kind in (
        ("artifacts", "baseline", EvidenceKind.SCREENSHOT),
        ("design_reports", "design", EvidenceKind.DESIGN_REPORT),
        ("device_captures", "device", EvidenceKind.DEVICE_SCREENSHOT),
        ("interaction_states", "interaction", EvidenceKind.INTERACTION_SCREENSHOT),
        ("scroll_timeline", "timeline", None),
        ("capture_quality", "capture_quality", None),
        ("errors", "error", None),
    ):
        for i, raw in enumerate(rows(manifest.get(key))):
            row = obj(raw)
            url = row.get("url")
            if not isinstance(url, str) or url not in index:
                continue
            view = row.get("id") if kind == "device" else row.get("viewport")
            default = "captured" if kind in ("baseline", "design") else "unknown"
            if kind == "error":
                default = "failed"
            status = row.get("status", default)
            if not isinstance(status, str):
                status = "unknown"
            index[url].append(PageEvidence(
                kind, view if isinstance(view, str) else None, status, quality(row),
                ref(bundle, "capture-manifest.json", f"/{key}/{i}"),
                ref(bundle, row.get("path"), kind=artifact_kind) if artifact_kind else None,
            ))
    result = []
    seen = set()
    for i, url in enumerate(routes):
        if url in seen:
            continue
        seen.add(url)
        evidence = tuple(index[url])
        limits = []
        if not any(e.kind == "baseline" and e.artifact for e in evidence):
            limits.append("baseline_not_recorded")
        if not any(e.kind == "design" and e.artifact for e in evidence):
            limits.append("design_not_recorded")
        if any(e.quality in ("warning", "invalid") for e in evidence):
            limits.append("capture_quality_issue")
        if any(e.kind == "error" or e.status in ("failed", "partial", "skipped", "not_attempted") for e in evidence):
            limits.append("incomplete_capture")
        try:
            route = urlsplit(url).path or "/"
        except ValueError:
            route = url
            limits.append("invalid_route_url")
        result.append(Page(
            stable_id("PAGE", bundle.run_id, url), url, route,
            ref(bundle, "routes.json", f"/{i}"), evidence, tuple(limits),
        ))
    return tuple(result)
