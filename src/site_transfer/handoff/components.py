"""Conservative sampled component inventory; no cross-viewport identity claims."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import isfinite

from .models import EvidenceBundle, EvidenceKind, EvidenceRef
from .pages import PREFIX, obj, rows, ref, stable_id, quality

_TAGS = {
    "header": "header", "footer": "footer", "nav": "navigation", "main": "main",
    "aside": "aside", "section": "section", "article": "article", "form": "form",
    "button": "button", "a": "link", "input": "input", "select": "select",
    "textarea": "textarea", "img": "image", "video": "video", "dialog": "dialog",
    "summary": "summary", "ul": "list", "ol": "list", "table": "table",
}
_ROLES = {
    "banner": "header", "contentinfo": "footer", "navigation": "navigation",
    "main": "main", "complementary": "aside", "dialog": "dialog",
    "button": "button", "link": "link", "form": "form", "region": "section",
    "tablist": "tablist", "tab": "tab", "list": "list", "img": "image",
}
_SIGNATURE_STYLE = ("display", "position", "flex-direction", "grid-template-columns",
                    "font-family", "font-size", "background-color", "gap")


@dataclass(frozen=True, slots=True)
class Component:
    id: str
    page_id: str
    url: str
    viewport: str
    selector: str
    kind: str
    confidence: str
    parent_id: str | None
    measurement: EvidenceRef
    screenshot: EvidenceRef | None
    screenshot_quality: str
    screenshot_mapping: str
    rect: tuple[float, float, float, float] | None
    styles: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SharedCandidate:
    id: str
    component_ids: tuple[str, ...]
    basis: str = "matching sampled subtree and computed style; reuse not verified"


@dataclass(frozen=True, slots=True)
class ComponentMap:
    components: tuple[Component, ...]
    shared_candidates: tuple[SharedCandidate, ...]
    limitations: tuple[str, ...]


def _kind(row):
    role = row.get("role")
    tag = row.get("tag")
    if isinstance(role, str) and role in _ROLES:
        return _ROLES[role], "observed"
    if isinstance(tag, str) and tag in _TAGS:
        return _TAGS[tag], "observed"
    if obj(row.get("style")).get("display") in ("grid", "inline-grid", "flex", "inline-flex"):
        return "layout_container", "observed"
    return None


def _rect(row):
    rect = obj(row.get("rect"))
    values = tuple(rect.get(k) for k in ("x", "y", "width", "height"))
    if all(type(v) in (int, float) and isfinite(v) for v in values) and values[2] > 0 and values[3] > 0:
        return values
    return None


def _parent(row):
    value = row.get("parent_selector")
    return value if isinstance(value, str) else None


def build_component_map(bundle: EvidenceBundle) -> ComponentMap:
    manifest = bundle.document(PREFIX + "capture-manifest.json")
    routes = set(bundle.document(PREFIX + "routes.json"))
    artifacts = {}
    for raw in rows(manifest.get("artifacts")):
        row = obj(raw)
        if isinstance(row.get("path"), str):
            artifacts[row["path"]] = row
    components = []
    groups = defaultdict(list)
    limits = {"sampled_dom_only", "selectors_are_snapshot_local", "screenshot_coordinates_not_verified"}
    seen_reports = set()
    for raw in rows(manifest.get("design_reports")):
        record = obj(raw)
        path = record.get("path")
        if not isinstance(path, str) or path in seen_reports:
            continue
        seen_reports.add(path)
        report = obj(bundle.documents.get(PREFIX + path))
        url, view = report.get("url"), report.get("viewport_name")
        if not isinstance(url, str) or url not in routes or not isinstance(view, str) or not view:
            limits.add("unattributed_design_report")
            continue
        if record.get("url", url) != url or record.get("viewport", view) != view:
            limits.add("design_identity_conflict")
            continue
        screenshot_path = report.get("screenshot")
        screenshot = None
        screenshot_quality = "unknown"
        if isinstance(screenshot_path, str):
            image = artifacts.get(screenshot_path, {})
            if image.get("url") == url and image.get("viewport") == view:
                screenshot = ref(bundle, screenshot_path, kind=EvidenceKind.SCREENSHOT)
                screenshot_quality = quality(image)
        if not screenshot:
            limits.add("unmatched_screenshot")
        if ref(bundle, path, kind=EvidenceKind.DESIGN_REPORT) is None:
            limits.add("unavailable_design_report")
            continue
        elements = rows(report.get("elements"))
        counts = Counter(obj(r).get("selector") for r in elements if isinstance(obj(r).get("selector"), str) and obj(r).get("selector"))
        by_selector = {obj(r)["selector"]: obj(r) for r in elements
                       if isinstance(obj(r).get("selector"), str) and counts[obj(r)["selector"]] == 1}
        if any(n > 1 for n in counts.values()):
            limits.add("ambiguous_selector")
        children = defaultdict(list)
        for selector, row in by_selector.items():
            children[_parent(row)].append(selector)
        candidates = {s: _kind(r) for s, r in by_selector.items() if _kind(r)}
        ids = {s: stable_id("CMP", bundle.run_id, path, s) for s in candidates}
        truncated = obj(obj(report.get("summary")).get("limits")).get("dom_truncated")
        if truncated:
            limits.add("dom_sample_truncated")
        for i, raw_row in enumerate(elements):
            row = obj(raw_row)
            selector = row.get("selector")
            if not isinstance(selector, str) or selector not in candidates:
                continue
            kind, confidence = candidates[selector]
            parent = _parent(row)
            visited = {selector}
            parent_id = None
            while parent in by_selector and parent not in visited:
                visited.add(parent)
                if parent in ids:
                    parent_id = ids[parent]
                    break
                parent = _parent(by_selector[parent])
            # Parent chain must be acyclic even if a selected parent was found early.
            cursor = _parent(row)
            chain = {selector}
            while cursor in by_selector:
                if cursor in chain:
                    parent_id = None
                    limits.add("cyclic_parent_metadata")
                    break
                chain.add(cursor)
                cursor = _parent(by_selector[cursor])
            styles = tuple(sorted((k, v) for k, v in obj(row.get("style")).items()
                                  if isinstance(k, str) and isinstance(v, str) and v))
            component = Component(
                ids[selector], stable_id("PAGE", bundle.run_id, url), url, view,
                selector, kind, confidence, parent_id,
                ref(bundle, path, f"/elements/{i}", EvidenceKind.DESIGN_REPORT),
                screenshot, screenshot_quality, "context_only" if screenshot else "unavailable",
                _rect(row), styles,
            )
            components.append(component)
            # Group only cross-page candidates, within the same viewport.
            # A bounded, nonempty sampled subtree is required; no merge of instances.
            if (kind in ("header", "footer", "navigation") and truncated is False
                    and not any(n > 1 for n in counts.values())):
                direct = children.get(selector, [])
                if direct and len(direct) <= 40:
                    def fingerprint(s, depth, visited):
                        if s in visited:
                            return None
                        r = by_selector[s]
                        descendants = children.get(s, [])
                        if len(descendants) > 40 or (depth == 0 and descendants):
                            return None
                        parts = [fingerprint(c, depth - 1, visited | {s}) for c in descendants]
                        if any(p is None for p in parts):
                            return None
                        return (str(r.get("tag", "")), str(r.get("role", "")),
                                tuple(str(obj(r.get("style")).get(k, "")) for k in _SIGNATURE_STYLE),
                                tuple(parts))
                    signature = fingerprint(selector, 3, set())
                    if signature is not None:
                        groups[(view, kind, signature)].append(component)
    shared = []
    for key, group in groups.items():
        if len({c.url for c in group}) > 1:
            ids = tuple(sorted(c.id for c in group))
            shared.append(SharedCandidate(stable_id("SHARED", bundle.run_id, *ids), ids))
    return ComponentMap(tuple(components), tuple(sorted(shared, key=lambda c: c.id)), tuple(sorted(limits)))
