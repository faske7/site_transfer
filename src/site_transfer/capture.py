"""Collect screenshots and immutable per-run manifests using Chromium."""
import hashlib
import json
import os
from pathlib import Path

from .browser import chromium, context_for, origin, public_url
from .discovery import normalize, seed_routes
from .measurements import measure
from .design_tokens import summarize, aggregate
from .interactions import inspect_interactions

DEFAULT_VIEWPORTS = [
    {"name": "desktop", "width": 1440, "height": 900},
    {"name": "mobile", "width": 390, "height": 844},
]


def write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def capture_site(config, root: Path, progress=lambda data: None):
    expected = public_url(config["source"]["url"])
    routes, limit = seed_routes(config)
    views = config.get("viewports", DEFAULT_VIEWPORTS)
    if len(views) > 4 or any(v["width"] > 2560 or v["height"] > 2160 for v in views):
        raise ValueError("Capture supports up to four viewports of at most 2560 x 2160")
    if config.get("browser", {}).get("headless", True) is False:
        raise ValueError("Docker capture is headless only")
    root.mkdir(parents=True, exist_ok=False)
    artifacts = []
    errors = []
    design_entries = []
    measurements = config.get('measurements', {}).get('enabled', True)
    interactions = config.get('interactions', {}).get('enabled', True)
    done = 0
    timeout = min(config.get("browser", {}).get("timeout_ms", 30000), 30000)

    def record():
        data = {"routes": list(routes), "artifacts": list(artifacts), "errors": list(errors),
                "completed": done, "total": len(routes) * len(views)}
        if measurements or interactions:
            data["design_reports"] = [{k: v for k, v in entry.items() if k != "summary"} for entry in design_entries]
            data["design_tokens"] = "design-tokens.json"
            write_json(root / "design-tokens.json", aggregate(design_entries))
        write_json(root / "routes.json", routes)
        write_json(root / "capture-manifest.json", data)
        progress(data)
        return data

    record()
    with chromium() as browser:
        index = 0
        while index < len(routes):
            url = routes[index]
            for view_index, viewport in enumerate(views):
                context = context_for(browser, viewport, expected)
                try:
                    page = context.new_page()
                    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    if response is None or response.status >= 400 or origin(page.url) != expected:
                        raise ValueError("Page failed or redirected outside source origin")
                    page.wait_for_timeout(700)
                    if origin(page.url) != expected:
                        raise ValueError("Page redirected outside source origin")
                    if view_index == 0 and config.get("discovery", {}).get("enabled", True):
                        links = page.locator("a[href]").evaluate_all("(nodes) => nodes.slice(0, 2000).map(a => a.href)")
                        for link in links:
                            candidate = normalize(page.url, link, expected)
                            if candidate and candidate not in routes and len(routes) < limit:
                                routes.append(candidate)
                    dimensions = page.evaluate("() => ({w: Math.max(document.documentElement.scrollWidth, innerWidth), h: Math.max(document.documentElement.scrollHeight, innerHeight)})")
                    if dimensions["h"] > 16000 or dimensions["w"] > 4096 or dimensions["h"] * dimensions["w"] > 40000000:
                        raise ValueError("Page exceeds full-page screenshot safety limits")
                    name = f"{index + 1:03d}-{hashlib.sha256(url.encode()).hexdigest()[:12]}.png"
                    relative = Path("screenshots") / viewport["name"] / name
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    snapshot = None
                    if measurements or interactions:
                        try:
                            snapshot = measure(page, measurements, interactions)
                        except Exception as exc:
                            errors.append({"url": url, "viewport": viewport["name"], "stage": "design", "error": str(exc)[:500]})
                    page.screenshot(path=str(target), full_page=True, animations="disabled", timeout=timeout)
                    artifacts.append({"path": relative.as_posix(), "url": url, "viewport": viewport["name"],
                                      "width": viewport["width"], "height": viewport["height"],
                                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
                    if snapshot is not None:
                        try:
                            summary = summarize(snapshot)
                            states = inspect_interactions(page, snapshot) if interactions else None
                            report_path = Path("design") / viewport["name"] / (Path(name).stem + ".json")
                            report_target = root / report_path
                            report_target.parent.mkdir(parents=True, exist_ok=True)
                            report = {"schema_version": 1, "url": url, "viewport_name": viewport["name"],
                                      "screenshot": relative.as_posix(), "summary": summary,
                                      "elements": snapshot["elements"], "interactions": states}
                            write_json(report_target, report)
                            design_entries.append({"path": report_path.as_posix(), "url": url, "viewport": viewport["name"],
                                                   "screenshot_index": len(artifacts)-1, "element_count": summary["element_count"],
                                                   "hover_count": len(states["hover"]) if states else 0,
                                                   "animation_count": len(summary["motion"]["observed"]),
                                                   "summary": summary})
                        except Exception as exc:
                            errors.append({"url": url, "viewport": viewport["name"], "stage": "design", "error": str(exc)[:500]})
                except Exception as exc:
                    errors.append({"url": url, "viewport": viewport["name"], "error": str(exc)[:500]})
                finally:
                    context.close()
                done += 1
                record()
            index += 1
    return record()
