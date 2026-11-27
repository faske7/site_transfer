import hashlib
import json
import pytest

from site_transfer.handoff import build_structure, load_evidence


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def element(selector, tag, parent=None, **styles):
    return {"selector": selector, "tag": tag, "role": "", "parent_selector": parent,
            "rect": {"x": 0, "y": 0, "width": 100, "height": 20}, "style": styles}


@pytest.fixture
def saved(tmp_path):
    root = tmp_path
    routes = ["https://example.com/", "https://example.com/contact", "https://example.com/missing"]
    manifest = {"routes": routes, "artifacts": [], "design_reports": [],
                "design_tokens": "design-tokens.json",
                "errors": [{"url": routes[2], "viewport": "mobile", "stage": "capture"}]}
    for i, url in enumerate(routes[:2]):
        name = f"screenshots/desktop/{i}.png"
        image = root / name
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"fixture")
        manifest["artifacts"].append({"path": name, "url": url, "viewport": "desktop",
            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "quality": {"status": "valid" if i == 0 else "warning"}})
        path = f"design/desktop/{i}.json"
        manifest["design_reports"].append({"path": path, "url": url, "viewport": "desktop"})
        write(root, path, {"url": url, "viewport_name": "desktop", "screenshot": name,
            "summary": {"limits": {"dom_truncated": False}},
            "elements": [element("header", "header", None, **{"display": "flex", "gap": "12px"}),
                         element("wrapper", "div", "header"),
                         element("nav", "nav", "wrapper", **{"font-family": "Helvetica"}),
                         element("button", "button", "nav", **{"color": "rgb(0, 0, 0)"})]})
    write(root, "routes.json", routes)
    write(root, "capture-manifest.json", manifest)
    write(root, "design-tokens.json", {"tokens": {"spacing": {"gap": [{"value": "12px", "count": 9}]}}})
    return root, {"id": "structure-fixture", "status": "partial", "manifest": manifest}


def change_report(saved, index, change):
    root, _ = saved
    path = f"design/desktop/{index}.json"
    doc = json.loads((root / path).read_text())
    change(doc)
    write(root, path, doc)


def build(saved):
    root, job = saved
    bundle = load_evidence(job, root)
    return bundle, build_structure(bundle)


def resolve(bundle, reference):
    file = next(f for f in bundle.files.values() if f.id == reference.evidence_id)
    if reference.json_pointer is None:
        return file
    current = bundle.document(file.path)
    for part in reference.json_pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, tuple) else current[key]
    return current


def test_pages_and_component_links(saved):
    bundle, result = build(saved)
    assert [p.page.route for p in result.pages] == ["/", "/contact", "/missing"]
    assert [len(p.component_ids) for p in result.pages] == [3, 3, 0]
    assert "baseline_not_recorded" in result.pages[2].page.limitations
    assert "capture_quality_issue" in result.pages[1].page.limitations
    for page in result.pages:
        assert resolve(bundle, page.page.route_ref) == page.page.url
        for item in page.page.evidence:
            assert resolve(bundle, item.record)["url"] == page.page.url
            if item.artifact:
                resolve(bundle, item.artifact)
    for component in result.components.components:
        assert resolve(bundle, component.measurement)["selector"] == component.selector
        assert component.screenshot_mapping == "context_only"
        assert resolve(bundle, component.screenshot).path.endswith(".png")


def test_hierarchy_and_shared_candidates(saved):
    _, result = build(saved)
    components = result.components.components[:3]
    header, nav, button = components
    assert header.parent_id is None
    assert nav.parent_id == header.id
    assert button.parent_id == nav.id
    assert all(c.confidence == "observed" for c in components)
    assert len(result.components.shared_candidates) == 2
    assert len({c.id for c in result.components.components}) == 6


def test_design_values_have_exact_pointers(saved):
    bundle, result = build(saved)
    gap = next(v for v in result.design.component_values if v.property == "gap")
    assert gap.count == 2
    assert gap.value == "12px"
    assert all(resolve(bundle, u.evidence) == gap.value for u in gap.uses)
    token = result.design.captured_tokens[0]
    assert token.count == 9
    assert resolve(bundle, token.evidence)["value"] == "12px"


def test_stable_result(saved):
    assert build(saved)[1] == build(saved)[1]


def test_mismatched_screenshot_not_linked(saved):
    change_report(saved, 0, lambda d: d.update(screenshot="screenshots/desktop/1.png"))
    _, result = build(saved)
    assert all(c.screenshot is None for c in result.components.components[:3])
    assert "unmatched_screenshot" in result.components.limitations


def test_mismatched_route_report_excluded(saved):
    change_report(saved, 0, lambda d: d.update(url="https://example.com/contact"))
    _, result = build(saved)
    assert not result.pages[0].component_ids
    assert "design_identity_conflict" in result.components.limitations


def test_different_styles_not_shared(saved):
    change_report(saved, 1, lambda d: d["elements"][0]["style"].update(gap="99px"))
    _, result = build(saved)
    groups = result.components.shared_candidates
    headers = {c.id for c in result.components.components if c.kind == "header"}
    assert not any(headers.intersection(g.component_ids) for g in groups)


def test_duplicate_selectors_excluded(saved):
    change_report(saved, 0, lambda d: d["elements"].append(d["elements"][2]))
    _, result = build(saved)
    assert not any(c.kind == "navigation" and c.url.endswith(".com/") for c in result.components.components)
    assert "ambiguous_selector" in result.components.limitations
    assert not result.components.shared_candidates


def test_cycle_never_links_parents(saved):
    change_report(saved, 0, lambda d: d["elements"][0].update(parent_selector="nav"))
    _, result = build(saved)
    assert all(c.parent_id is None for c in result.components.components[:3])
    assert "cyclic_parent_metadata" in result.components.limitations


def test_truncated_report_not_shared(saved):
    change_report(saved, 0, lambda d: d["summary"]["limits"].update(dom_truncated=True))
    _, result = build(saved)
    assert "dom_sample_truncated" in result.components.limitations
    assert not result.components.shared_candidates


def test_legacy_without_design(saved):
    root, job = saved
    job["manifest"].pop("design_reports")
    job["manifest"].pop("design_tokens")
    write(root, "capture-manifest.json", job["manifest"])
    _, result = build(saved)
    assert len(result.pages) == 3
    assert not result.components.components
    assert not result.design.component_values
    assert "aggregate_tokens_unavailable" in result.design.limitations
