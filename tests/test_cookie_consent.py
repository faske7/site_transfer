import pytest
from contextlib import nullcontext

from site_transfer.browser import origin
from site_transfer.config import ConfigError, validate_config
from site_transfer.cookie_consent import handle_cookie_consent
from site_transfer.pipeline import CaptureCancelled

URL="https://example.com/"
OPTIONS={"enabled":True,"timeout_ms":2000}
HTML="""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
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
    page.route("**/*",lambda r:r.fulfill(status=200,content_type="text/html; charset=utf-8",body=html)
               if r.request.url==URL else r.abort())
    page.goto(URL)


@pytest.mark.parametrize("strategy,choice",[("reject_optional","reject"),("accept_all","accept")])
def test_czech_consent(page,strategy,choice):
    load(page,HTML)
    assert page.evaluate("document.characterSet")=="UTF-8"
    assert page.locator("#reject").inner_text()=="Odmítnout vše"
    assert page.locator("#accept").inner_text()=="Přijmout vše"
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


@pytest.mark.parametrize("with_scroll_content,reload,custom",[(True,False,False),(False,False,False),(True,True,False),(True,False,True)],
                         ids=["visible-content","blank-viewport","same-url-reload","custom-spa-banner"])
def test_capture_pipeline_consent(browser,tmp_path,monkeypatch,with_scroll_content,reload,custom):
    from site_transfer import capture, device_capture, interaction_capture
    from site_transfer.browser import context_for as real_context
    from site_transfer.manifest import build_kit
    from zipfile import ZipFile
    import json
    from PIL import Image

    # The heading alone is above the viewport after scrolling 600 CSS px.
    # A successful state must contain real visible reference content.
    html=HTML.replace('<h1>Reference content</h1>',
        '<h1>Reference content</h1><section style="position:absolute;top:650px;left:0;right:0;height:700px;background:#174ea6;color:white"><h2>Scrolled reference content</h2></section>') if with_scroll_content else HTML

    if custom:
        import json
        custom_body=CUSTOM_HTML.split('<h1>Reference</h1>',1)[1]
        html=html.split('<div id="cookie-banner">',1)[0]
        html+='<script>setTimeout(()=>history.replaceState({ready:true},"",location.href),250);'
        html+=f'setTimeout(()=>document.body.insertAdjacentHTML("beforeend",{json.dumps(custom_body)}),500);</script>'

    if reload:
        html=html.replace("window.choice='reject';this.parentElement.remove()",
                          "sessionStorage.setItem('consent','yes');location.reload()")
        html+="<script>if(sessionStorage.getItem('consent'))document.querySelector('#cookie-banner').remove()</script>"

    def context(browser,viewport,expected,network_gate=None,device_options=None):
        ctx=real_context(browser,viewport,expected,network_gate,device_options)
        def route(r):
            if r.request.url==URL and not (network_gate and network_gate["closed"]):
                r.fulfill(status=200,content_type="text/html; charset=utf-8",body=html)
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
         "browser":{"cookie_consent":dict(OPTIONS,timeout_ms=4000) if reload or custom else OPTIONS},
         "viewports":[{"name":"mobile","width":390,"height":844}],
         "discovery":{"enabled":False,"max_pages":1},
         "interactions":{"enabled":True,"scenarios":[{"id":"scroll","route":"/","action":"scroll","scroll_y":600}]},
         "measurements":{"device_emulation":{"max_routes":1}}}
    root=tmp_path/"run"
    manifest=capture.capture_site(cfg,root)
    diagnostic=json.dumps({"errors":manifest["errors"],"states":manifest["interaction_states"]},ensure_ascii=False,indent=2)
    for key in ("artifacts","capture_quality","device_captures","interaction_states"):
        assert len(manifest[key])==1,diagnostic
        assert manifest[key][0]["cookie_consent"]["status"]=="dismissed",diagnostic
        if reload:
            assert manifest[key][0]["cookie_consent"]["code"]=="banner_hidden_after_reload",diagnostic
        if custom:
            assert manifest[key][0]["cookie_consent"]["navigation"]["same_url_history_events"]>=1,diagnostic
    state=manifest["interaction_states"][0]
    assert state["after"]["scroll_y"]==600,diagnostic
    expected_path="interactions/mobile/scroll.png"
    if with_scroll_content:
        assert not manifest["errors"],diagnostic
        assert state["status"]=="captured",diagnostic
        assert state["path"]==expected_path
        with Image.open(root/state["path"]) as image:
            # Center of the viewport must show the blue section, not a banner.
            assert image.convert("RGB").getpixel((image.width//2,image.height//2))==(23,78,166)
    else:
        assert state["status"]=="failed",diagnostic
        assert state["failure_stage"]=="validation",diagnostic
        assert state["code"]=="white_png",diagnostic
        assert len(manifest["errors"])==1,diagnostic
        assert manifest["errors"][0]["code"]=="white_png",diagnostic
        assert "path" not in state and not (root/expected_path).exists()
    output=tmp_path/"kit.zip"
    build_kit(cfg,{"id":"fixture","status":"completed" if with_scroll_content else "partial","manifest":manifest},root,output)
    with ZipFile(output) as archive:
        saved=json.loads(archive.read("design/reference/capture-manifest.json"))
        assert saved==manifest
        assert ("design/reference/"+expected_path in archive.namelist())==with_scroll_content


def test_same_url_reload_after_consent(page):
    html="""<meta charset="utf-8"><h1>Reference content</h1>
    <div id="cookie-banner">Cookies<button onclick="sessionStorage.setItem('consent','yes');location.reload()">Reject all</button></div>
    <script>if(sessionStorage.getItem('consent'))document.querySelector('#cookie-banner').remove()</script>"""
    load(page,html)
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=4000))
    assert result["status"]=="dismissed",result
    assert result["code"]=="banner_hidden_after_reload",result
    assert result["navigation"]["same_url_reload"] is True
    assert result["navigation"]["document_requests"]==1
    assert page.url==URL
    assert page.evaluate("sessionStorage.getItem('consent')")=="yes"


def test_reload_without_dismissal(page):
    load(page,'<div id="cookie-banner">Cookies<button onclick="location.reload()">Reject all</button></div>')
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=3000))
    assert result["status"]=="unresolved",result
    assert result["code"]=="banner_still_visible"
    assert result["navigation"]["same_url_reload"] is True
    assert result["navigation"]["document_requests"]==1


def test_navigation_to_other_route_rejected(page):
    html='<div id="cookie-banner">Cookies<button onclick="location.href=\'/other\'">Reject all</button></div>'
    page.route("**/*",lambda r:r.fulfill(status=200,content_type="text/html; charset=utf-8",
               body=html if r.request.url==URL else "<h1>Other route</h1>"))
    page.goto(URL)
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=3000))
    assert result["status"]=="failed",result
    assert result["code"]=="navigation_changed"
    assert result["navigation"]["same_url_reload"] is False


def test_navigation_before_click_rejected(page):
    load(page,"<h1>Reference</h1><script>setTimeout(()=>location.reload(),300)</script>")
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=3000))
    assert result["status"]=="failed",result
    assert result["code"]=="navigation_changed"
    assert result["clicked"] is False
    assert result["navigation"]["phase"]=="before_click"


def test_repeated_reload_rejected(page):
    html="""<h1>Reference</h1>
    <div id="cookie-banner">Cookies<button onclick="sessionStorage.setItem('consent','yes');location.reload()">Reject all</button></div>
    <script>if(sessionStorage.getItem('consent'))setTimeout(()=>location.reload(),200)</script>"""
    load(page,html)
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=4000))
    assert result["status"]=="failed",result
    assert result["code"]=="navigation_changed"
    assert result["navigation"]["reason"]=="repeated_navigation"


def test_popup_rejected(page):
    load(page,'<div id="cookie-banner">Cookies<button onclick="window.open(\'about:blank\');this.parentElement.remove()">Reject all</button></div>')
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=3000))
    assert result["status"]=="failed",result
    assert result["code"]=="navigation_changed"
    assert result["navigation"]["reason"]=="popup"


CUSTOM_HTML="""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<h1>Reference</h1>
<div class="fixed bottom-0" style="position:fixed;bottom:0;left:0;right:0;background:white">
  <div class="container"><p>Na tomto webu používáme soubory cookies.</p>
    <div class="actions">
      <button onclick="window.choice='reject';this.closest('.fixed').remove()">Odmítnout vše</button>
      <button onclick="window.choice='accept';this.closest('.fixed').remove()">Souhlasím se všemi</button>
    </div>
  </div>
</div>"""


@pytest.mark.parametrize("strategy,choice",[("accept_all","accept"),("reject_optional","reject")])
def test_custom_czech_banner(page,strategy,choice):
    load(page,CUSTOM_HTML)
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy=strategy,timeout_ms=4000))
    assert result["status"]=="dismissed",result
    assert page.evaluate("window.choice")==choice
    assert not page.locator(".fixed").count()


@pytest.mark.parametrize("method",["replaceState","pushState"])
def test_exact_url_history_during_hydration(page,method):
    # No candidate until after the same-document event, as observed on RE/MAX.
    import json
    body=CUSTOM_HTML.split('<h1>Reference</h1>',1)[1]
    load(page,'<meta charset="utf-8"><h1>Reference</h1><script>'
         f'setTimeout(()=>history.{method}({{ready:true}},"",location.href),250);'
         f'setTimeout(()=>document.body.insertAdjacentHTML("beforeend",{json.dumps(body)}),500);'
         '</script>')
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy="accept_all",timeout_ms=4000))
    assert result["status"]=="dismissed",result
    assert result["navigation"]["same_url_history_events"]>=1
    assert result["navigation"]["document_requests"]==0
    assert result["navigation"]["document_commits"]==0
    assert page.evaluate("window.choice")=="accept"


@pytest.mark.parametrize("destination",["/other","/?changed=1","/#changed"])
def test_history_route_change_rejected(page,destination):
    import json
    load(page,f'<h1>Reference</h1><script>setTimeout(()=>history.replaceState({{}},"",{json.dumps(destination)}),250)</script>')
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,timeout_ms=3000))
    assert result["status"]=="failed",result
    assert result["code"]=="navigation_changed"
    assert not result["clicked"]


def test_custom_overlay_without_cookie_context(page):
    load(page,CUSTOM_HTML.replace("Na tomto webu používáme soubory cookies.","Review the proposed changes."))
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy="accept_all"))
    assert result["status"]=="not_detected",result
    assert not result["clicked"]


def test_custom_static_controls_not_clicked(page):
    load(page,CUSTOM_HTML.replace("position:fixed","position:static"))
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy="accept_all"))
    assert result["status"]=="not_detected",result
    assert not result["clicked"]


def test_custom_root_remaining_after_controls_removed(page):
    load(page,CUSTOM_HTML.replace("this.closest('.fixed').remove()","this.closest('.actions').remove()"))
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy="accept_all",timeout_ms=3000))
    assert result["status"]=="unresolved",result
    assert page.locator(".fixed").is_visible()


def test_custom_banner_requires_opposing_choice(page):
    load(page,CUSTOM_HTML.replace("Odmítnout vše","Settings"))
    result=handle_cookie_consent(page,origin(URL),dict(OPTIONS,strategy="accept_all"))
    assert result["status"]=="not_detected",result
    assert not result["clicked"]
