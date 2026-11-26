"""Actual Chromium profile + full capture integration using test-only responses."""
import hashlib
import json
from contextlib import nullcontext
from zipfile import ZipFile

import pytest

from site_transfer.device_capture import profiles, device_options, planned_devices, registry_entry
from site_transfer.manifest import device_files, build_kit
from site_transfer.responsive_probes import declared_boundaries
from site_transfer.config import validate_config, ConfigError
from site_transfer.browser import origin


def test_profiles():
    assert [(p["width"],p["height"],p["dpr"]) for p in profiles()]==[
        (390,844,3),(412,915,2.625),(768,1024,2),
        (1366,768,1),(1440,900,1),(1920,1080,1)]
    for p in profiles():
        options=device_options(p,"141.0.0.0")
        assert options["viewport"]==options["screen"]=={"width":p["width"],"height":p["height"]}
        assert options["device_scale_factor"]==p["dpr"]
        assert options["has_touch"]==p["has_touch"]
        assert options["is_mobile"]==p["is_mobile"]


def test_boundaries():
    result=declared_boundaries(["(max-width: 768px)","(min-width:768px)","(min-width: 40em)",
                                "(orientation: portrait)","(min-width: 1024px)"])
    assert [p["width"] for p in result]==[768,1024]
    assert len(result[0]["conditions"])==2


@pytest.mark.parametrize("limit",[0,6])
def test_device_budget_config(limit):
    with pytest.raises(ConfigError):
        validate_config({"source":{"url":"https://example.com"},"target":{"project_name":"demo"},
                         "measurements":{"device_emulation":{"max_routes":limit}}})


def test_device_path_validation():
    entry=planned_devices("https://example.com/")[0]
    assert device_files({})=={}
    manifest={"device_manifest":"device-manifest.json","device_sha256":"a"*64,
              "device_captures":[dict(entry,status="captured",path="../secret.png",sha256="b"*64)]}
    with pytest.raises(ValueError):
        device_files(manifest)


def test_device_pipeline(browser_fixture,tmp_path,monkeypatch):
    from site_transfer import capture, device_capture
    from site_transfer.browser import context_for as real_context_for
    from site_transfer.manifest import digest
    from PIL import Image

    html="""<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{margin:0;font:16px Arial} main{display:grid;grid-template-columns:1fr 1fr;gap:24px}
    @media(max-width:768px){main{grid-template-columns:1fr;gap:8px}}</style>
    <main><h1>Fixture</h1><p>Device evidence</p></main>"""
    def fixture_context(browser,viewport,expected,network_gate=None,device_options=None):
        ctx=real_context_for(browser,viewport,expected,network_gate,device_options)
        def respond(route):
            if route.request.url=="https://example.com/":
                route.fulfill(status=200,content_type="text/html",body=html)
            else:
                route.fallback()
        ctx.route("**/*",respond)
        return ctx
    monkeypatch.setattr(capture,"chromium",lambda:nullcontext(browser_fixture))
    monkeypatch.setattr(capture,"public_url",origin)
    monkeypatch.setattr(capture,"context_for",fixture_context)
    monkeypatch.setattr(device_capture,"context_for",fixture_context)
    cfg={"source":{"url":"https://example.com"},"target":{"project_name":"demo"},
         "discovery":{"enabled":False,"max_pages":1},"interactions":{"enabled":False},
         "measurements":{"device_emulation":{"max_routes":1}}}
    root=tmp_path/"run"
    manifest=capture.capture_site(cfg,root)
    assert manifest["errors"]==[],manifest["errors"]
    assert len(manifest["artifacts"])==2
    assert len(manifest["device_captures"])==6
    report=json.loads((root/"device-manifest.json").read_text())
    assert [registry_entry(d) for d in report["devices"]]==manifest["device_captures"]
    for entry in manifest["device_captures"]:
        assert entry["status"]=="captured",entry
        observed=entry["observed"]
        assert observed["screen_width"]==entry["width"]
        assert observed["screen_height"]==entry["height"]
        assert observed["dpr"]==pytest.approx(entry["dpr"])
        assert (observed["max_touch_points"]>0)==entry["has_touch"]
        with Image.open(root/entry["path"]) as image:
            assert image.width==entry["width"]
        assert digest(root/entry["path"])==entry["sha256"]
    assert digest(root/"device-manifest.json")==manifest["device_sha256"]
    output=tmp_path/"kit.zip"
    job={"id":"fixture","status":"completed","manifest":manifest}
    build_kit(cfg,job,root,output)
    with ZipFile(output) as archive:
        assert "design/reference/device-manifest.json" in archive.namelist()
        assert len([n for n in archive.namelist() if n.startswith("design/reference/devices/")])==6
    (root/manifest["device_captures"][0]["path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError,match="checksum"):
        build_kit(cfg,job,root,tmp_path/"bad.zip")


@pytest.fixture
def browser_fixture():
    pw=pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as playwright:
        try:
            browser=playwright.chromium.launch(headless=True)
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Chromium not installed")
            raise
        try:
            yield browser
        finally:
            browser.close()
