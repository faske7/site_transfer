import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from contextlib import nullcontext

import pytest
from PIL import Image
from site_transfer.config import validate_config,ConfigError
from site_transfer.scroll_timeline import visual_diff,compare_motion
from site_transfer.manifest import build_kit

URL="https://example.com/"


def png(color):
    out=BytesIO()
    Image.new("RGB",(20,20),color).save(out,format="PNG")
    return out.getvalue()


def test_visual_difference():
    assert visual_diff(png("white"),png("white"))[0]==0
    assert visual_diff(png("black"),png("white"))[0]==100


def test_motion_excludes_normal_scroll():
    el={"id":1,"x":0,"y":200,"width":50,"height":50,"position":"static",
        "opacity":"1","transform":"none"}
    previous={"scroll_y":0,"visible_elements":[el]}
    current={"scroll_y":100,"visible_elements":[dict(el,y=100)]}
    assert compare_motion(previous,current)==[]
    current["visible_elements"][0]["transform"]="matrix(1,0,0,1,5,0)"
    assert len(compare_motion(previous,current))==1


def config():
    return {"source":{"url":URL},"target":{"project_name":"demo"},
            "viewports":[{"name":"desktop","width":800,"height":600}],
            "discovery":{"enabled":False,"max_pages":1},
            "measurements":{"enabled":False},"interactions":{"enabled":False},
            "assets":{"enabled":False},
            "scroll_timeline":{"enabled":True,"routes":["/"],"profiles":[
                {"viewport":"desktop","step_px":500,"settle_ms":200}],
                "stable_steps":3,"max_frames":12,"timeout_ms":20000}}


@pytest.mark.parametrize("change",[{"routes":["/missing"]},{"profiles":[{"viewport":"unknown"}]},
    {"profiles":[{"viewport":"desktop"},{"viewport":"desktop"}]},{"max_frames":151},
    {"max_frames":6,"stable_steps":6}])
def test_invalid_timeline_config(change):
    cfg=config()
    cfg["scroll_timeline"].update(change)
    with pytest.raises(ConfigError):
        validate_config(cfg)


@pytest.fixture
def browser():
    pw=pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b=p.chromium.launch(headless=True)
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Chromium not installed")
            raise
        try:
            yield b
        finally:
            b.close()


@pytest.mark.parametrize("max_frames,expected_status",[(12,"captured"),(6,"partial")])
def test_timeline_pipeline_and_zip(browser,tmp_path,monkeypatch,max_frames,expected_status):
    from site_transfer import capture,scroll_timeline
    from site_transfer.browser import context_for as real_context,origin
    html="""<!doctype html><meta charset="utf-8"><style>
    body{margin:0} section{height:600px;background:#174ea6;color:white}
    section:nth-child(2n){background:#973a25} .moving{position:fixed;top:30px;left:30px;color:white}
    </style><div class="moving">Balloon</div>
    <section>One</section><section>Two</section><section>Three</section><section>Four</section>
    <script>addEventListener('scroll',()=>document.querySelector('.moving').style.transform=
        'translateX('+scrollY/10+'px)')</script>"""
    def context(browser,viewport,expected,*args,**kwargs):
        ctx=real_context(browser,viewport,expected,*args,**kwargs)
        ctx.route("**/*",lambda r:r.fulfill(status=200,content_type="text/html",body=html)
                  if r.request.url==URL else r.fallback())
        return ctx
    monkeypatch.setattr(capture,"chromium",lambda:nullcontext(browser))
    monkeypatch.setattr(capture,"public_url",origin)
    monkeypatch.setattr(capture,"context_for",context)
    monkeypatch.setattr(scroll_timeline,"context_for",context)
    cfg=config()
    cfg["scroll_timeline"]["max_frames"]=max_frames
    root=tmp_path/"run"
    manifest=capture.capture_site(cfg,root)
    sequence=manifest["scroll_timeline"][0]
    assert sequence["status"]==expected_status,sequence
    assert sequence["frames"][0]["scroll_y"]==0
    assert any(f["visual_diff_percent"] and f["visual_diff_percent"]>0 for f in sequence["frames"])
    assert any(f["motion_count"]>0 for f in sequence["frames"])
    if expected_status=="captured":
        assert sequence["stop_reason"]=="bottom_reached"
        assert sequence["frames"][-1]["at_bottom"]
        assert sequence["frames"][-1]["stable_count"]>=3
    else:
        assert sequence["stop_reason"]=="max_frames"
    output=tmp_path/"kit.zip"
    build_kit(cfg,{"id":"fixture","status":"completed" if expected_status=="captured" else "partial",
                  "manifest":manifest},root,output)
    with ZipFile(output) as archive:
        names=archive.namelist()
        for frame in sequence["frames"]:
            assert "design/reference/"+frame["screenshot"]["path"] in names
            if frame["index"]:
                assert "design/reference/"+frame["difference_map"]["path"] in names
        assert "design/reference/scroll-timeline-manifest.json" in names
        overview=sequence["horizontal_storyboard"]
        assert overview["status"]=="derived",overview
        assert overview["method"]=="chronological_viewport_storyboard_v1"
        assert "design/reference/"+overview["image"]["path"] in names
        import hashlib
        assert hashlib.sha256(archive.read("design/reference/"+overview["image"]["path"])).hexdigest()==overview["image"]["sha256"]
    (root/sequence["frames"][0]["screenshot"]["path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError,match="checksum"):
        build_kit(cfg,{"id":"fixture","status":"partial","manifest":manifest},root,output)
