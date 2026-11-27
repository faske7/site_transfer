import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from site_transfer.config import validate_config, ConfigError
from site_transfer.interaction_capture import planned_states, capture_state, observe, SkippedState
from site_transfer.manifest import build_kit, interaction_files
from site_transfer.pipeline import CaptureCancelled
from site_transfer.browser import origin


def config(scenarios):
    return {"source":{"url":"https://example.com","pages":["/"]},
            "target":{"project_name":"fixture"},
            "discovery":{"enabled":False,"max_pages":1},
            "interactions":{"enabled":True,"scenarios":scenarios}}


def scenario(**changes):
    return dict(id="menu",route="/",action="click",selector="#menu",**{}) | changes


@pytest.mark.parametrize("changes", [
    {"selector":"button"}, {"selector":"#x, #y"}, {"action":"submit"},
    {"route":"//other.example/"}, {"route":"/missing"}, {"viewports":["unknown"]},
    {"action":"scroll"}, {"wait_ms":1501}, {"id":"../escape"},
])
def test_invalid_state(changes):
    with pytest.raises(ConfigError):
        validate_config(config([scenario(**changes)]))


def test_duplicate_id():
    with pytest.raises(ConfigError):
        validate_config(config([scenario(),scenario(selector="#other")]))


def test_plan_viewports():
    cfg=validate_config(config([scenario(viewports=["mobile"])]))
    states=planned_states(cfg,["https://example.com/"],[
        {"name":"desktop","width":1440,"height":900},{"name":"mobile","width":390,"height":844}])
    assert len(states)==1 and states[0]["viewport"]=="mobile"
    assert states[0]["status"]=="not_attempted"


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


HTML = """<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{height:2500px} #hover:hover{color:red} #focus:focus{outline:3px solid red}</style>
<button id="menu" onclick="document.querySelector('#panel').hidden=false;fetch('/write',{method:'POST'}).catch(()=>{})">Menu</button>
<div id="panel" hidden>Menu contents</div>
<button id="modal" onclick="document.querySelector('#dialog').showModal()">Modal</button>
<dialog id="dialog">Dialog contents</dialog>
<details><summary id="accordion">Details</summary><p id="details">Details content</p></details>
<button id="hover">Hover</button><button id="focus">Focus</button>
<form><button id="submit">Send</button></form>
<a id="link" href="/other">Link</a><button id="delete">Delete</button>
"""


@pytest.mark.parametrize("width,action,selector,expect",[
    (1440,"click","#menu","#panel"),(390,"click","#menu","#panel"),
    (1440,"click","#modal","#dialog"),(390,"click","#modal","#dialog"),
    (1440,"click","#accordion","#details"),(390,"click","#accordion","#details"),
    (1440,"hover","#hover",None),(1440,"focus","#focus",None),
    (390,"focus","#focus",None),(1440,"scroll",None,None),(390,"scroll",None,None),
])
def test_real_browser_states(browser,width,action,selector,expect):
    context=browser.new_context(viewport={"width":width,"height":844},
                                is_mobile=width<600,has_touch=width<600)
    try:
        page=context.new_page()
        page.set_content(HTML)
        before,after,verified=observe(page,dict(action=action,selector=selector,
            expect_visible=expect,width=width,scroll_y=600,wait_ms=10))
        if expect:
            assert verified is True
        if action=="scroll":
            assert after["scroll_y"]==600
        if action=="hover":
            assert after["target"]["hovered"]
        if action=="focus":
            assert after["target"]["focused"]
    finally:
        context.close()


@pytest.mark.parametrize("selector",["#submit","#link","#delete","#missing"])
def test_unsafe_controls_skipped(browser,selector):
    page=browser.new_page()
    try:
        page.set_content(HTML)
        with pytest.raises(SkippedState):
            observe(page,dict(action="click",selector=selector,width=1440,wait_ms=0))
    finally:
        page.close()


def test_real_capture_and_offline_gate(browser,tmp_path,monkeypatch):
    # Test-only synthetic HTTP response; production public DNS/SSRF policy untouched.
    from site_transfer import interaction_capture as module
    original=module.context_for
    requests=[]
    def fixture_context(browser,viewport,expected,network_gate):
        ctx=original(browser,viewport,expected,network_gate)
        def fixture_route(route):
            if network_gate["closed"]:
                network_gate["blocked"]+=1
                route.abort()
            elif route.request.url=="https://example.com/":
                route.fulfill(status=200,content_type="text/html",body=HTML)
            else:
                requests.append(route.request.url)
                route.abort()
        ctx.route("**/*",fixture_route)
        return ctx
    monkeypatch.setattr(module,"context_for",fixture_context)
    view={"name":"mobile","width":390,"height":844}
    state=planned_states(config([scenario(expect_visible="#panel")]),["https://example.com/"],[view])[0]
    result=capture_state(browser,view,origin(state["url"]),tmp_path,state)
    assert result["status"]=="captured",result
    assert result["expectation_verified"] is True
    assert result["network_mode"]=="offline"
    assert not requests
    assert result["sha256"]==hashlib.sha256((tmp_path/result["path"]).read_bytes()).hexdigest()
    assert (tmp_path/result["path"]).read_bytes().startswith(b"\x89PNG")
    with pytest.raises(CaptureCancelled):
        capture_state(browser,view,origin(state["url"]),tmp_path,state,lambda:True)


def test_kit_state_evidence(tmp_path):
    root=tmp_path/"run"
    baseline=root/"screenshots/desktop/base.png"
    image=root/"interactions/desktop/menu.png"
    for path in (baseline,image):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(path.name.encode())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    states=[dict(id="menu",viewport="desktop",status="captured",path="interactions/desktop/menu.png",sha256=sha(image)),
            dict(id="missing",viewport="desktop",status="skipped",reason="not found")]
    report=root/"interaction-manifest.json"
    report.write_text(json.dumps({"schema_version":1,"states":states}))
    manifest={"artifacts":[{"path":"screenshots/desktop/base.png","sha256":sha(baseline)}],
              "interaction_manifest":"interaction-manifest.json","interaction_sha256":sha(report),
              "interaction_states":states,"errors":[]}
    (root/"routes.json").write_text("[]")
    (root/"capture-manifest.json").write_text(json.dumps(manifest))
    job={"id":"run","status":"partial","manifest":manifest}
    output=tmp_path/"kit.zip"
    build_kit(config([]),job,root,output)
    with ZipFile(output) as archive:
        assert "design/reference/interactions/desktop/menu.png" in archive.namelist()
        assert "design/reference/interaction-manifest.json" in archive.namelist()
        assert not any("missing.png" in name for name in archive.namelist())
    image.write_bytes(b"tampered")
    with pytest.raises(ValueError,match="checksum"):
        build_kit(config([]),job,root,output)
    states[0]["path"]="../escape.png"
    with pytest.raises(ValueError):
        interaction_files(manifest)


@pytest.mark.parametrize("with_scenarios", [False, True])
def test_full_capture_with_design_and_interactions(browser, tmp_path, monkeypatch, with_scenarios):
    """Exercise the actual capture_site loop, not only individual state probes."""
    from contextlib import nullcontext
    from site_transfer import capture, interaction_capture
    from site_transfer.browser import context_for as real_context_for

    def fixture_context(browser, viewport, expected, network_gate=None):
        ctx = real_context_for(browser, viewport, expected, network_gate)
        def fixture_route(route):
            if route.request.url == "https://example.com/" and not (
                network_gate and network_gate.get("closed")
            ):
                route.fulfill(status=200, content_type="text/html", body=HTML)
            else:
                route.fallback()
        ctx.route("**/*", fixture_route)
        return ctx

    monkeypatch.setattr(capture, "chromium", lambda: nullcontext(browser))
    monkeypatch.setattr(capture, "public_url", origin)
    monkeypatch.setattr(capture, "context_for", fixture_context)
    monkeypatch.setattr(interaction_capture, "context_for", fixture_context)
    cfg = config([scenario(expect_visible="#panel")] if with_scenarios else [])
    cfg["measurements"] = {"device_emulation":{"enabled":False}}
    root = tmp_path / "run"
    manifest = capture.capture_site(cfg, root)
    assert manifest["errors"] == []
    assert manifest["completed"] == manifest["total"] == 2
    assert len(manifest["artifacts"]) == len(manifest["design_reports"]) == 2
    assert json.loads((root / "capture-manifest.json").read_text()) == manifest
    for entry in manifest["design_reports"]:
        report = json.loads((root / entry["path"]).read_text())
        assert isinstance(report["interactions"]["hover"], list)
        assert report["schema_version"] == 2
        assert "advanced" in report["summary"]
        if entry["viewport"] == "desktop":
            assert entry["probe_count"] == 5
            assert report["responsive_probes"]["status"] == "observed"
        else:
            assert report["responsive_probes"]["status"] == "skipped"
    if with_scenarios:
        states = manifest["interaction_states"]
        assert len(states) == 2
        assert {s["viewport"] for s in states} == {"desktop", "mobile"}
        for state in states:
            assert state["id"] == "menu"
            assert state["status"] == "captured", state
            assert state["expectation_verified"] is True
            assert manifest["artifacts"][state["baseline_index"]]["viewport"] == state["viewport"]
            assert hashlib.sha256((root / state["path"]).read_bytes()).hexdigest() == state["sha256"]
        report = root / "interaction-manifest.json"
        assert json.loads(report.read_text())["states"] == states
        assert hashlib.sha256(report.read_bytes()).hexdigest() == manifest["interaction_sha256"]
    else:
        assert "interaction_states" not in manifest
        assert not (root / "interaction-manifest.json").exists()
    output = tmp_path / "kit.zip"
    build_kit(cfg, {"id":"fixture", "status":"completed", "manifest":manifest}, root, output)
    with ZipFile(output) as archive:
        assert ("design/reference/interaction-manifest.json" in archive.namelist()) == with_scenarios
        assert len([name for name in archive.namelist() if name.startswith("design/reference/interactions/")]) == (2 if with_scenarios else 0)


@pytest.mark.parametrize("scrollable",[True,False])
def test_delayed_scroll_state_diagnostics(browser,tmp_path,monkeypatch,scrollable):
    from site_transfer import interaction_capture as module
    original=module.context_for
    html="""<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
    <h1>Loading</h1><script>setTimeout(()=>{
       document.body.innerHTML='<h1>Ready</h1><div style="height:2400px;background:blue"></div>';
    },1500)</script>""" if scrollable else "<h1>Short document</h1>"
    def fixture_context(browser,viewport,expected,network_gate):
        ctx=original(browser,viewport,expected,network_gate)
        def route(r):
            if r.request.url=="https://example.com/" and not network_gate["closed"]:
                r.fulfill(status=200,content_type="text/html",body=html)
            else:
                r.fallback()
        ctx.route("**/*",route)
        return ctx
    monkeypatch.setattr(module,"context_for",fixture_context)
    view={"name":"desktop","width":400,"height":300}
    state=planned_states(config([scenario(id="scroll",action="scroll",selector=None,scroll_y=600)]),
                         ["https://example.com/"],[view])[0]
    result=capture_state(browser,view,origin(state["url"]),tmp_path,state)
    if scrollable:
        assert result["status"]=="captured",result
        assert result["after"]["scroll_y"]==600
        assert result["readiness"]["sample"]["scrollable"]>=600
    else:
        assert result["status"]=="failed"
        assert result["code"]=="scroll_unchanged"
        assert result["failure_stage"]=="action"
        assert result["before"]["scroll_y"]==result["after"]["scroll_y"]==0
        assert "path" not in result


@pytest.mark.parametrize("case",["lazy_chunk","crash","navigation"])
def test_guarded_scroll_lazy_loading(browser,tmp_path,monkeypatch,case):
    """Synthetic public routes; actual request guard handles disallowed requests."""
    from site_transfer import interaction_capture as module
    real_context=module.context_for
    loaded=[]
    gates=[]
    html="""<!doctype html><meta charset="utf-8">
    <style>body{margin:0;background:#ace;min-height:3000px}
    #ready{position:fixed;top:30px;background:blue;color:white}
    </style><h1>Reference</h1><div style="height:3000px;background:linear-gradient(red,blue)"></div>
    <script>
    let started=false;
    addEventListener('scroll',()=>{
        if(scrollY<500 || started)return;
        started=true;
        fetch('/write',{method:'POST'}).catch(()=>{});
        const script=document.createElement('script');
        script.src='/lazy.js';
        script.onerror=()=>{
            document.body.style.minHeight='0';
            document.body.innerHTML='<h2>Application error: a client-side exception has occurred (see the browser console for more information).</h2>';
        };
        document.head.append(script);
    });
    </script>"""
    lazy_js=("location.href='/other';" if case=="navigation" else
             "document.body.insertAdjacentHTML('beforeend','<div id=\"ready\">Lazy content</div>');"
             "console.error('Benign third-party error');")
    def fixture_context(browser,viewport,expected,network_gate):
        ctx=real_context(browser,viewport,expected,network_gate)
        gates.append(network_gate)
        def fixture_route(route):
            request=route.request
            if not network_gate["closed"] and request.method=="GET":
                if request.url=="https://example.com/":
                    route.fulfill(status=200,content_type="text/html",body=html)
                    return
                if request.url=="https://example.com/lazy.js":
                    loaded.append(True)
                    if case=="crash":
                        route.abort()
                    else:
                        route.fulfill(status=200,content_type="application/javascript",body=lazy_js)
                    return
            # POST and main-frame navigation are handled by the real guard.
            route.fallback()
        ctx.route("**/*",fixture_route)
        return ctx
    monkeypatch.setattr(module,"context_for",fixture_context)
    view={"name":"desktop","width":800,"height":600}
    state=planned_states(config([scenario(id="scroll",action="scroll",selector=None,
                scroll_y=600,wait_ms=500,expect_visible="#ready" if case=="lazy_chunk" else None)]),
                ["https://example.com/"],[view])[0]
    result=capture_state(browser,view,origin(state["url"]),tmp_path,state)
    assert loaded,result
    assert result["network_mode"]=="guarded_scroll"
    assert result["blocked_requests"]>=1,result
    assert gates[0]["scroll_read_only"] and not gates[0]["closed"]
    assert result["main_navigation_blocked"] is (case=="navigation"),result
    if case=="lazy_chunk":
        assert result["status"]=="captured",result
        assert result["after"]["scroll_y"]==600
        assert result["expectation_verified"] is True
        assert (tmp_path/result["path"]).is_file()
    else:
        assert result["status"]=="failed",result
        assert result["code"]==("application_crash" if case=="crash" else "navigation_changed"),result
        assert "path" not in result
        assert not list(tmp_path.rglob("*.png"))


def test_application_crash_marker_is_top_level(browser):
    from site_transfer.interaction_capture import reject_application_crash,StateFailure
    page=browser.new_page()
    try:
        page.set_content('<h1>Healthy page</h1><iframe srcdoc="Application error: a client-side exception has occurred"></iframe>')
        reject_application_crash(page)
        page.set_content('<h1>Healthy page</h1><div hidden>Application error: a client-side exception has occurred</div>')
        reject_application_crash(page)
        page.set_content('<h2>Application error: a client-side exception has occurred (see the browser console for more information).</h2>')
        with pytest.raises(StateFailure) as exc:
            reject_application_crash(page)
        assert exc.value.code=="application_crash"
    finally:
        page.close()


def test_navigation_takes_priority_over_scroll_failure(browser,tmp_path,monkeypatch):
    from site_transfer import interaction_capture as module
    real_context=module.context_for
    gates=[]
    def fixture_context(browser,viewport,expected,network_gate):
        gates.append(network_gate)
        ctx=real_context(browser,viewport,expected,network_gate)
        ctx.route("https://example.com/",lambda route:route.fulfill(
            status=200,content_type="text/html",
            body='<h1>Reference</h1><div style="height:3000px;background:blue"></div>'))
        return ctx
    def interrupted_observe(page,state,cancelled):
        gates[0]["navigation_attempted"]=True
        raise module.StateFailure("scroll_unchanged","No movement",
                                  before={"scroll_y":0},after={"scroll_y":0})
    monkeypatch.setattr(module,"context_for",fixture_context)
    monkeypatch.setattr(module,"observe",interrupted_observe)
    view={"name":"desktop","width":800,"height":600}
    state=planned_states(config([scenario(id="scroll",action="scroll",selector=None,scroll_y=600)]),
                         ["https://example.com/"],[view])[0]
    result=capture_state(browser,view,origin(state["url"]),tmp_path,state)
    assert result["status"]=="failed",result
    assert result["code"]=="navigation_changed",result
    assert result["main_navigation_blocked"] is True
    assert result["before"]["scroll_y"]==result["after"]["scroll_y"]==0
    assert "path" not in result
    assert not list(tmp_path.rglob("*.png"))
