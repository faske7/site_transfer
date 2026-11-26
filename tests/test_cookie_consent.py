import pytest
from contextlib import nullcontext

from site_transfer.browser import origin
from site_transfer.config import ConfigError, validate_config
from site_transfer.cookie_consent import handle_cookie_consent
from site_transfer.pipeline import CaptureCancelled

URL="https://example.com/"
OPTIONS={"enabled":True,"timeout_ms":2000}
HTML="""<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{height:1800px} #cookie-banner{position:fixed;inset:0;background:white;z-index:999}</style>
<h1>Reference content</h1>
<div id="cookie-banner">Cookies
<button id="reject" onclick="window.choice='reject';this.parentElement.remove()">Odmítnout vše</button>
<button id="accept" onclick="window.choice='accept';this.parentElement.remove()">Přijmout vše</button>
</div>"""


@pytest.fixture
def browser():
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


@pytest.fixture
def page(browser):
    page=browser.new_page()
    try:
        yield page
    finally:
        page.close()


def load(page,html):
    page.route("**/*",lambda r:r.fulfill(status=200,content_type="text/html",body=html)
               if r.request.url==URL else r.abort())
    page.goto(URL)


@pytest.mark.parametrize("strategy,choice",[("reject_optional","reject"),("accept_all","accept")])
def test_czech_consent(page,strategy,choice):
    load(page,HTML)
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy=strategy))
    assert result["status"]=="dismissed",result
    assert page.evaluate("window.choice")==choice
    assert not page.locator("#cookie-banner").count()


def test_disabled_no_click(page):
    load(page,HTML)
    assert handle_cookie_consent(page,origin(URL))["status"]=="disabled"
    assert page.locator("#cookie-banner").is_visible()


def test_reject_never_accepts(page):
    load(page,HTML.replace('Odmítnout vše','Settings'))
    result=handle_cookie_consent(page,origin(URL),OPTIONS)
    assert result["status"]=="unresolved"
    assert not result["clicked"]
    assert page.locator("#cookie-banner").is_visible()


def test_delayed_banner(page):
    load(page,"<h1>Reference</h1><script>setTimeout(()=>document.body.insertAdjacentHTML('beforeend',"
         "'<div id=\"cookie-banner\">Cookies<button onclick=\"this.parentElement.remove()\">Reject all</button></div>'),400)</script>")
    assert handle_cookie_consent(page,origin(URL),OPTIONS)["status"]=="dismissed"


def test_unrelated_button_not_clicked(page):
    load(page,"<h1>Reference</h1><button onclick=\"window.clicked=true\">Accept all</button>")
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=1000,strategy="accept_all"))
    assert result["status"]=="not_detected"
    assert not result["clicked"]


def test_ambiguous_button(page):
    load(page,HTML.replace('Přijmout vše','Odmítnout vše'))
    result=handle_cookie_consent(page,origin(URL),OPTIONS)
    assert result["code"]=="ambiguous_control"
    assert not result["clicked"]


def test_form_button_rejected(page):
    load(page,'<div id="cookie-banner">Cookies<form><button>Reject all</button></form></div>')
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=1000))
    assert result["status"]=="unresolved"
    assert not result["clicked"]


def test_manual_selector(page):
    load(page,HTML.replace('Odmítnout vše','Custom localized label'))
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy="manual_selector",
         detect_automatically=False,banner_selector="#cookie-banner",selectors=["#reject"]))
    assert result["status"]=="dismissed",result
    assert page.evaluate("window.choice")=="reject"


def test_unchanged_banner_no_repeated_click(page):
    load(page,'<div id="cookie-banner">Cookies<button onclick="window.clicks=(window.clicks||0)+1">Reject all</button></div>')
    result=handle_cookie_consent(page,origin(URL),OPTIONS)
    assert result["code"]=="banner_still_visible",result
    assert page.evaluate("window.clicks")==1


def test_cancel(page):
    load(page,HTML)
    with pytest.raises(CaptureCancelled):
        handle_cookie_consent(page,origin(URL),OPTIONS,lambda:True)
    assert page.locator("#cookie-banner").is_visible()


@pytest.mark.parametrize("changes",[
    {"strategy":"unknown"}, {"timeout_ms":9000}, {"selectors":["button"]},
    {"strategy":"manual_selector"}, {"detect_automatically":False},
    {"selectors":["#reject"]}, {"arbitrary_js":"alert(1)"},
])
def test_invalid_config(changes):
    config={"source":{"url":URL},"target":{"project_name":"demo"},
            "browser":{"cookie_consent":dict(OPTIONS,**changes)}}
    with pytest.raises(ConfigError):
        validate_config(config)


def test_capture_pipeline_consent(browser,tmp_path,monkeypatch):
    from site_transfer import capture, device_capture, interaction_capture
    from site_transfer.browser import context_for as real_context
    from site_transfer.manifest import build_kit
    from zipfile import ZipFile
    import json

    def context(browser,viewport,expected,network_gate=None,device_options=None):
        ctx=real_context(browser,viewport,expected,network_gate,device_options)
        def route(r):
            if r.request.url==URL and not (network_gate and network_gate["closed"]):
                r.fulfill(status=200,content_type="text/html",body=HTML)
            else:
                r.fallback()
        ctx.route("**/*",route)
        return ctx

    monkeypatch.setattr(capture,"chromium",lambda:nullcontext(browser))
    monkeypatch.setattr(capture,"public_url",origin)
    for module in (capture,device_capture,interaction_capture):
        monkeypatch.setattr(module,"context_for",context)
    real_devices=capture.planned_devices
    monkeypatch.setattr(capture,"planned_devices",lambda url:real_devices(url)[:1])
    cfg={"source":{"url":URL,"pages":["/"]},"target":{"project_name":"demo"},
         "browser":{"cookie_consent":OPTIONS},
         "viewports":[{"name":"mobile","width":390,"height":844}],
         "discovery":{"enabled":False,"max_pages":1},
         "interactions":{"enabled":True,"scenarios":[{"id":"scroll","route":"/","action":"scroll","scroll_y":600}]},
         "measurements":{"device_emulation":{"max_routes":1}}}
    root=tmp_path/"run"
    manifest=capture.capture_site(cfg,root)
    assert not manifest["errors"],manifest["errors"]
    for key in ("artifacts","capture_quality","device_captures","interaction_states"):
        assert len(manifest[key])==1
        assert manifest[key][0]["cookie_consent"]["status"]=="dismissed",manifest[key][0]
    assert manifest["interaction_states"][0]["after"]["scroll_y"]==600
    output=tmp_path/"kit.zip"
    build_kit(cfg,{"id":"fixture","status":"completed","manifest":manifest},root,output)
    with ZipFile(output) as archive:
        saved=json.loads(archive.read("design/reference/capture-manifest.json"))
        assert saved==manifest
