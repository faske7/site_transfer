"""Real Chromium regression fixtures for scroll input and measured progress."""
from time import monotonic

import pytest
from site_transfer.scroll_engine import ScrollEngine
from site_transfer.scroll_detection import snapshot_scroll,classify
from site_transfer.interaction_capture import observe,StateFailure
from site_transfer.pipeline import CaptureCancelled

BASE='<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'

@pytest.fixture
def page():
    pw=pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            browser=p.chromium.launch(headless=True)
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Chromium not installed")
            raise
        context=browser.new_context(viewport={"width":800,"height":600})
        try:
            yield context.new_page()
        finally:
            context.close()
            browser.close()


def test_vertical_exact_target(page):
    page.set_content(BASE+'<body style="height:2000px"><h1>Reference</h1></body>')
    engine=ScrollEngine(page)
    result=engine.scroll_to(600,50,monotonic()+6)
    assert result["target_reached"] is True,result
    assert result["after"]["scroll_y"]==600
    assert result["modes"]==["vertical"]


def test_horizontal_document(page):
    page.set_content(BASE+'<body style="margin:0;width:2200px;height:500px"><h1>Horizontal</h1></body>')
    engine=ScrollEngine(page)
    for _ in range(12):
        engine.step(400,150,monotonic()+3)
        if engine.end():
            break
    assert "horizontal" in engine.modes,engine.summary()
    assert engine.end()
    assert snapshot_scroll(page)["root"]["y"]==0


def test_nested_vertical(page):
    page.set_content(BASE+'''<style>body{margin:0;overflow:hidden}
    #panel{position:absolute;left:10px;top:10px;width:300px;height:500px;overflow:auto}
    </style><div id="panel"><div style="height:1600px;background:blue">Nested</div></div>''')
    engine=ScrollEngine(page)
    for _ in range(12):
        engine.step(400,150,monotonic()+3)
        if engine.end():
            break
    assert {"nested","vertical"}.issubset(engine.modes),engine.summary()
    assert engine.end()
    assert page.evaluate("scrollY")==0


def test_nested_horizontal(page):
    page.set_content(BASE+'''<style>body{margin:0;overflow:hidden}
    #panel{position:absolute;left:10px;top:10px;width:300px;height:400px;overflow:auto}
    </style><div id="panel"><div style="width:1400px;height:200px;background:blue">Nested</div></div>''')
    engine=ScrollEngine(page)
    for _ in range(16):
        engine.step(400,150,monotonic()+3)
        if engine.end():
            break
    assert {"nested","horizontal"}.issubset(engine.modes),engine.summary()
    assert engine.end()


def test_transform_only_not_false_failure_or_completion(page):
    page.set_content(BASE+'''<style>body{overflow:hidden}.scene{width:200px;height:200px;background:blue}</style>
    <div class="scene">Scene</div><script>let n=0;addEventListener('wheel',e=>{
    e.preventDefault();n+=e.deltaY;document.querySelector('.scene').style.transform='translateX('+n/10+'px)';
    },{passive:false})</script>''')
    before,after,_=observe(page,dict(action="scroll",width=800,scroll_y=600,wait_ms=100))
    report=after["scroll_observation"]
    assert before["scroll_y"]==after["scroll_y"]==0
    assert report["modes"]==["transform"],report
    assert report["target_reached"] is None
    engine=ScrollEngine(page)
    engine.step(200,100,monotonic()+3)
    assert not engine.end()


def test_hybrid_vertical_transform(page):
    page.set_content(BASE+'''<body style="height:2000px"><div id="scene" style="position:fixed;top:0">Scene</div>
    <script>addEventListener('scroll',()=>document.querySelector('#scene').style.transform=
    'translateX('+scrollY/10+'px)')</script></body>''')
    engine=ScrollEngine(page)
    engine.step(300,150,monotonic()+3)
    assert {"vertical","transform"}.issubset(engine.modes),engine.summary()


def test_no_movement_is_failure(page):
    page.set_content(BASE+'<h1>Static</h1>')
    with pytest.raises(StateFailure) as error:
        observe(page,dict(action="scroll",width=800,scroll_y=600,wait_ms=20))
    assert error.value.code=="scroll_unchanged"


def test_idle_animation_not_progress():
    def sample(transform):
        return {"root":{"x":0,"y":0},"containers":[],"truncated":False,
                "transforms":[{"id":1,"transform":transform,"translate":"none","rotate":"none",
                               "scale":"none","position":"static","top":"auto","left":"auto"}]}
    result=classify(sample("matrix(1,0,0,1,2,0)"),sample("matrix(1,0,0,1,3,0)"),
                    sample("matrix(1,0,0,1,1,0)"))
    assert not result["progress"]
    assert result["idle_motion_count"]==1


def test_cancel_before_input(page):
    page.set_content(BASE+'<body style="height:2000px">Reference</body>')
    with pytest.raises(CaptureCancelled):
        ScrollEngine(page,lambda:True).step(300,150,monotonic()+3)
    assert page.evaluate("scrollY")==0
