"""Local routed browser fixtures; no external site or network required."""
from io import BytesIO
from time import monotonic

import pytest
from PIL import Image, ImageDraw

from site_transfer.browser import origin
from site_transfer.pipeline import CaptureCancelled
from site_transfer.reliable_capture import capture_png, QualityFailure
from site_transfer.screenshot_quality import inspect_png
from site_transfer.manifest import selected_files

URL="https://example.com/"

def png(color="white", mark=False):
    im=Image.new("RGB",(100,100),color)
    if mark:
        ImageDraw.Draw(im).rectangle((10,10,50,50),fill="blue")
    buf=BytesIO()
    im.save(buf,format="PNG")
    return buf.getvalue()

@pytest.mark.parametrize("data,code",[
    (b"","empty_png"),(b"not a png","corrupt_png"),
    (png(),"white_png"),(png("black"),"uniform_png"),
    (png()[:-20],"corrupt_png"),
])
def test_invalid_png(data,code):
    assert inspect_png(data)["code"]==code
    assert inspect_png(data)["status"]=="invalid"

def test_valid_and_pixel_budget():
    data=png(mark=True)
    assert inspect_png(data)["status"]=="valid"
    assert inspect_png(data,100)["code"]=="pixel_budget"

def test_old_manifest_and_invalid_evidence():
    entry={"path":"screenshots/desktop/a.png","sha256":"a"*64}
    assert selected_files({"artifacts":[entry]})[entry["path"]]==entry["sha256"]
    with pytest.raises(ValueError,match="Invalid screenshot evidence"):
        selected_files({"artifacts":[dict(entry,quality={"status":"invalid"})]})

@pytest.fixture
def page():
    pw=pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as playwright:
        try:
            browser=playwright.chromium.launch(headless=True)
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Chromium not installed")
            raise
        context=browser.new_context(viewport={"width":400,"height":300})
        p=context.new_page()
        try:
            yield p
        finally:
            context.close()
            browser.close()

def load(page,html):
    page.route("**/*",lambda route:route.fulfill(status=200,content_type="text/html",body=html)
               if route.request.url==URL else route.abort())
    page.goto(URL,wait_until="domcontentloaded")

def capture(page,tmp_path,**kwargs):
    return capture_png(page,tmp_path/"evidence.png",origin(URL),lambda:False,12000,**kwargs)

def test_delayed_hydration(page,tmp_path):
    load(page,"""<body><script>setTimeout(()=>document.body.innerHTML=
        '<h1>Hydrated</h1><div style="background:blue;height:90px"></div>',1200)</script></body>""")
    result=capture(page,tmp_path)
    assert result["status"]!="invalid"
    assert (tmp_path/"evidence.png").exists()

def test_delayed_image(page,tmp_path):
    load(page,"""<body><h1>Image</h1><img id="i" width="100" height="100">
       <script>setTimeout(()=>i.src='data:image/svg+xml,'+encodeURIComponent(
       '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="blue"/></svg>'),1000)</script>""")
    capture(page,tmp_path)
    assert page.locator("img").evaluate("(i)=>i.naturalWidth")==100

def test_lazy_and_reveal(page,tmp_path):
    load(page,"""<h1>Top</h1><div style="height:950px"></div>
    <div id="reveal" style="height:120px;opacity:0;background:blue"></div>
    <img id="lazy" width="100" height="100" loading="lazy">
    <script>const observer=new IntersectionObserver(entries=>entries.forEach(e=>{
    if(e.isIntersecting){e.target.style.opacity=1;
    if(e.target.id==='lazy')e.target.src='data:image/svg+xml,'+encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="red"/></svg>');
    observer.unobserve(e.target)}}));observer.observe(reveal);observer.observe(lazy)</script>""")
    result=capture(page,tmp_path)
    assert page.locator("#reveal").evaluate("(e)=>getComputedStyle(e).opacity")=="1"
    assert page.locator("#lazy").evaluate("(i)=>i.naturalWidth")==100
    assert page.evaluate("scrollY")==0
    assert result["attempts"][0]["scroll"]["steps"]>0

def test_infinite_animation_and_overflow(page,tmp_path):
    load(page,"""<style>@keyframes spin{to{transform:rotate(360deg)}}
    .box{width:600px;height:100px;background:blue;animation:spin 1s infinite}</style>
    <h1>Overflow</h1><div class="box"></div>""")
    start=monotonic()
    result=capture(page,tmp_path)
    assert monotonic()-start<15
    assert "document_overflow" in result["warnings"]

def test_blank_retry_exhaustion(page,tmp_path):
    load(page,"<body></body>")
    with pytest.raises(QualityFailure) as exc:
        capture(page,tmp_path)
    assert exc.value.quality["code"]=="retry_exhausted"
    assert len(exc.value.quality["attempts"])==2
    assert all(a["quality"]["code"]=="white_png" for a in exc.value.quality["attempts"])
    assert not (tmp_path/"evidence.png").exists()

def test_corruption_then_recovery(page,tmp_path,monkeypatch):
    load(page,"<h1>Content</h1><div style='background:red;height:80px'></div>")
    original=page.screenshot
    count=0
    def screenshot(**kwargs):
        nonlocal count
        count+=1
        return b"bad" if count==1 else original(**kwargs)
    monkeypatch.setattr(page,"screenshot",screenshot)
    result=capture(page,tmp_path)
    assert result["attempts"][0]["quality"]["code"]=="corrupt_png"
    assert count==2

def test_capture_timeout(page,tmp_path,monkeypatch):
    load(page,"<h1>Content</h1>")
    from playwright.sync_api import TimeoutError
    def timeout(**kwargs):
        raise TimeoutError("fixture timeout")
    monkeypatch.setattr(page,"screenshot",timeout)
    with pytest.raises(QualityFailure) as exc:
        capture(page,tmp_path)
    assert len(exc.value.quality["attempts"])==2
    assert all(a["quality"]["code"]=="capture_timeout" for a in exc.value.quality["attempts"])
    assert not (tmp_path/"evidence.png").exists()

def test_cancellation(page,tmp_path):
    load(page,"<h1>Content</h1>")
    calls=0
    def cancelled():
        nonlocal calls
        calls+=1
        return calls>=4
    with pytest.raises(CaptureCancelled):
        capture_png(page,tmp_path/"evidence.png",origin(URL),cancelled,12000)
    assert not (tmp_path/"evidence.png").exists()


def test_device_full_page_timeout_falls_back(page,tmp_path,monkeypatch):
    load(page,"<h1>Content</h1><div style='height:1200px;background:blue'></div>")
    original=page.screenshot
    calls=[]
    from playwright.sync_api import TimeoutError
    def screenshot(**kwargs):
        calls.append(kwargs)
        if kwargs["full_page"]:
            raise TimeoutError("fixture full-page timeout")
        return original(**kwargs)
    monkeypatch.setattr(page,"screenshot",screenshot)
    result=capture_png(page,tmp_path/"evidence.png",origin(URL),lambda:False,18000,device=True)
    assert [c["full_page"] for c in calls]==[True,False]
    assert calls[0]["timeout"]>=3000
    assert result["attempts"][0]["failure_stage"]=="screenshot"
    assert result["attempts"][1]["fallback_reason"]=="full_page_timeout"
    assert result["screenshot_mode"]=="viewport"
    assert "viewport_fallback" in result["warnings"]


def test_device_delayed_long_page(page,tmp_path):
    load(page,"""<body><script>setTimeout(()=>document.body.innerHTML=
        '<h1>Hydrated</h1><div style="background:blue;height:2200px"></div>',2200)</script></body>""")
    try:
        result=capture_png(page,tmp_path/"evidence.png",origin(URL),lambda:False,18000,device=True)
    except QualityFailure as exc:
        pytest.fail(repr(exc.quality))
    assert result["screenshot_mode"]=="full_page"
    assert result["attempts"][0]["readiness"]["status"]=="settled"
    assert result["attempts"][0]["readiness"]["sample"]["height"]>2000
    assert result["attempts"][0]["screenshot_timeout_ms"]>=3000


def test_script_only_shell_not_ready(page):
    from site_transfer.page_readiness import wait_ready
    load(page,"<body><script>window.fixtureLoaded=true</script></body>")
    result=wait_ready(page,monotonic()+.8,lambda:False,min_ms=100)
    assert result["status"]=="unsettled"
    assert result["sample"]["text"]==0
    assert result["sample"]["visual_hint"] is False


def test_text_free_visual_page_can_settle(page):
    from site_transfer.page_readiness import wait_ready
    load(page,"<body><div style='width:100px;height:100px;background:blue'></div></body>")
    result=wait_ready(page,monotonic()+2,lambda:False,min_ms=100)
    assert result["status"]=="settled"
    assert result["sample"]["text"]==0
    assert result["sample"]["visual_hint"] is True
