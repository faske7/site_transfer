"""Collect screenshots and immutable per-run manifests using Chromium."""
import hashlib
import json
import os
from pathlib import Path

from .browser import chromium, context_for, origin, public_url
from .discovery import normalize, seed_routes
from .measurements import measure
from .design_tokens import summarize, aggregate
from .design_report import build_report
from .device_capture import planned_devices, capture_device, registry_entry, LIMITATIONS as DEVICE_LIMITATIONS
from .responsive_probes import probe_widths, MAX_ROUTES, LIMITATIONS as PROBE_LIMITATIONS
from .interactions import inspect_interactions
from .interaction_capture import planned_states, capture_state, LIMITATIONS
from .config import validate_config
from .assets import inventory, combine
from .pipeline import CaptureCancelled
from .reliable_capture import capture_png, QualityFailure

DEFAULT_VIEWPORTS = [
    {"name": "desktop", "width": 1440, "height": 900},
    {"name": "mobile", "width": 390, "height": 844},
]


def write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def capture_site(config, root: Path, progress=lambda data: None, cancelled=lambda: False):
    validate_config(config)
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
    capture_quality = []
    design_entries = []
    asset_reports = []
    assets_enabled = config.get('assets', {}).get('enabled', True)
    measurements = config.get('measurements', {}).get('enabled', True)
    interactions = config.get('interactions', {}).get('enabled', True)
    device_config = config.get("measurements", {}).get("device_emulation", {})
    device_enabled = measurements and device_config.get("enabled", True)
    device_route_limit = device_config.get("max_routes", 3)
    device_entries = []
    scenario_states = planned_states(config, routes, views) if interactions else []
    done = 0
    timeout = min(config.get("browser", {}).get("timeout_ms", 30000), 30000)

    def record():
        data = {"routes": list(routes), "artifacts": list(artifacts), "errors": list(errors),
                "completed": done, "total": len(routes) * len(views),
                "capture_quality_version": 1, "capture_quality": list(capture_quality)}
        if measurements or interactions:
            data["design_reports"] = [{k: v for k, v in entry.items() if k != "summary"} for entry in design_entries]
            data["design_tokens"] = "design-tokens.json"
            write_json(root / "design-tokens.json", aggregate(design_entries))
        if assets_enabled:
            catalog = combine(asset_reports)
            data["asset_manifest"] = "asset-manifest.json"
            data["asset_count"] = catalog["count"]
            write_json(root / "asset-manifest.json", catalog)
        if scenario_states:
            interaction_report = {"schema_version": 1, "states": list(scenario_states), "limitations": LIMITATIONS}
            write_json(root / "interaction-manifest.json", interaction_report)
            data["interaction_manifest"] = "interaction-manifest.json"
            data["interaction_sha256"] = hashlib.sha256((root / "interaction-manifest.json").read_bytes()).hexdigest()
            data["interaction_states"] = list(scenario_states)
        if device_enabled:
            device_report = {"schema_version":1,"route_limit":device_route_limit,
                             "excluded_routes":list(routes[device_route_limit:]),
                             "devices":list(device_entries),"limitations":DEVICE_LIMITATIONS}
            write_json(root / "device-manifest.json", device_report)
            data["device_manifest"] = "device-manifest.json"
            data["device_sha256"] = hashlib.sha256((root / "device-manifest.json").read_bytes()).hexdigest()
            data["device_captures"] = [registry_entry(entry) for entry in device_entries]
            data["device_route_limit"] = device_route_limit
        write_json(root / "routes.json", routes)
        write_json(root / "capture-manifest.json", data)
        progress(data)
        return data

    record()
    with chromium() as browser:
        index = 0
        while index < len(routes):
            url = routes[index]
            probes_attempted = False
            for view_index, viewport in enumerate(views):
                if cancelled():
                    raise CaptureCancelled('Capture cancelled at viewport boundary')
                baseline_index = None
                context = context_for(browser, viewport, expected)
                try:
                    page = context.new_page()
                    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    if response is None or response.status >= 400 or origin(page.url) != expected:
                        raise ValueError("Page failed or redirected outside source origin")
                    name = f"{index + 1:03d}-{hashlib.sha256(url.encode()).hexdigest()[:12]}.png"
                    relative = Path("screenshots") / viewport["name"] / name
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    quality = capture_png(page, target, expected, cancelled, timeout)
                    capture_quality.append({"url":url,"viewport":viewport["name"],"quality":quality})
                    artifacts.append({"path": relative.as_posix(), "url": url, "viewport": viewport["name"],
                                      "width": viewport["width"], "height": viewport["height"],
                                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "quality": quality})
                    baseline_index = len(artifacts) - 1
                    if view_index == 0 and config.get("discovery", {}).get("enabled", True):
                        links = page.locator("a[href]").evaluate_all("(nodes) => nodes.slice(0, 2000).map(a => a.href)")
                        for link in links:
                            candidate = normalize(page.url, link, expected)
                            if candidate and candidate not in routes and len(routes) < limit:
                                routes.append(candidate)
                    if assets_enabled:
                        try:
                            asset_reports.append(inventory(page, url, viewport["name"]))
                        except Exception as exc:
                            errors.append({"url": url, "viewport": viewport["name"], "stage": "assets", "error": str(exc)[:500]})
                    snapshot = None
                    if measurements or interactions:
                        try:
                            snapshot = measure(page, measurements, interactions)
                        except Exception as exc:
                            errors.append({"url": url, "viewport": viewport["name"], "stage": "design", "error": str(exc)[:500]})
                    if snapshot is not None:
                        try:
                            summary = summarize(snapshot)
                            hover_observations = inspect_interactions(page, snapshot) if interactions else None
                            report_path = Path("design") / viewport["name"] / (Path(name).stem + ".json")
                            report_target = root / report_path
                            report_target.parent.mkdir(parents=True, exist_ok=True)
                            probes = {"status":"skipped","observations":[],"limitations":PROBE_LIMITATIONS,
                                      "reason":"Measurements disabled, non-desktop viewport, route budget or already probed"}
                            if measurements and viewport["width"] >= 600 and index < MAX_ROUTES and not probes_attempted:
                                probes_attempted = True
                                try:
                                    probes = probe_widths(page, snapshot, cancelled)
                                except CaptureCancelled:
                                    raise
                                except Exception:
                                    probes = {"status":"partial","observations":[],"limitations":PROBE_LIMITATIONS,
                                              "reason":"Responsive probe setup failed"}
                                if probes["status"] != "observed":
                                    errors.append({"url":url,"viewport":viewport["name"],"stage":"responsive",
                                                   "error":"Some responsive measurements unavailable"})
                            report = build_report(url, viewport["name"], relative.as_posix(), snapshot,
                                                  summary, hover_observations, probes)
                            write_json(report_target, report)
                            design_entries.append({"path": report_path.as_posix(), "url": url, "viewport": viewport["name"],
                                                   "screenshot_index": len(artifacts)-1, "element_count": summary["element_count"],
                                                   "hover_count": len(hover_observations["hover"]) if hover_observations else 0,
                                                   "animation_count": len(summary["motion"]["observed"]),
                                                   "report_schema_version": 2,
                                                   "probe_status": probes["status"],
                                                   "probe_count": sum(p["status"]=="observed" for p in probes["observations"]),
                                                   "summary": summary})
                        except CaptureCancelled:
                            raise
                        except Exception as exc:
                            errors.append({"url": url, "viewport": viewport["name"], "stage": "design", "error": str(exc)[:500]})
                except CaptureCancelled:
                    raise
                except QualityFailure as exc:
                    capture_quality.append({"url":url,"viewport":viewport["name"],"quality":exc.quality})
                    errors.append({"url":url,"viewport":viewport["name"],"stage":"quality",
                                   "code":exc.quality["code"],"error":str(exc)})
                except Exception as exc:
                    code="capture_timeout" if type(exc).__name__=="TimeoutError" else "capture_failed"
                    if baseline_index is None:
                        capture_quality.append({"url":url,"viewport":viewport["name"],"quality":{"status":"invalid","code":code}})
                    errors.append({"url": url, "viewport": viewport["name"], "stage":"capture", "code":code, "error":"Page load or capture failed"})
                finally:
                    context.close()
                done += 1
                record()
                for state_index, state in enumerate(scenario_states):
                    if state["url"] != url or state["viewport"] != viewport["name"]:
                        continue
                    if cancelled():
                        raise CaptureCancelled("Capture cancelled at interaction boundary")
                    if baseline_index is None:
                        result = dict(state, status="skipped", reason="Baseline unavailable")
                    else:
                        result = capture_state(browser, viewport, expected, root, state, cancelled)
                        result["baseline_index"] = baseline_index
                    scenario_states[state_index] = result
                    if result["status"] != "captured":
                        errors.append({"url": url, "viewport": viewport["name"], "stage": "interaction",
                                       "state_id": state["id"], "error": result["reason"],
                                       "code":result.get("code","state_unavailable"),"failure_stage":result.get("failure_stage")})
                    record()
            if device_enabled and index < device_route_limit:
                start = len(device_entries)
                device_entries.extend(planned_devices(url))
                record()
                for device_index in range(start,len(device_entries)):
                    device = device_entries[device_index]
                    if cancelled():
                        raise CaptureCancelled("Capture cancelled at device boundary")
                    result = capture_device(browser, expected, root, device, cancelled)
                    device_entries[device_index] = result
                    if result["status"] != "captured":
                        errors.append({"url":url,"viewport":device["id"],"stage":"device",
                                       "error":result["reason"],"code":result.get("quality",{}).get("code","device_failed")})
                    record()
            index += 1
    return record()
