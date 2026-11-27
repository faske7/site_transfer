"""Regression checks for bounded DOM caching and lossless pixel evidence."""
from io import BytesIO
from random import Random
import hashlib

import pytest
from PIL import Image, ImageChops

from site_transfer.scroll_detection import SAMPLE, snapshot_scroll
from site_transfer.scroll_timeline import SNAPSHOT, snapshot, write_bytes
from site_transfer.scroll_performance import PerformanceDiagnostics, release_dom_cache
from site_transfer.scroll_pixel_diff import PixelDiffSequence, visual_diff


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


@pytest.mark.parametrize("count",[5,5000,5005])
def test_shared_candidates(page,count):
    page.set_content("<div></div>"*count)
    diag=PerformanceDiagnostics()
    first=snapshot(page,True,diag)
    snapshot_scroll(page,diag)
    assert snapshot(page,True,diag)==first
    report=diag.report()
    assert report["dom_full_scans"]==1
    assert report["dom_cache_hits"]==2
    assert first["dom_count"]==count
    assert first["dom_sample_truncated"]==(count>5000)
    assert page.evaluate("document.__stScrollCandidateCacheV1.nodes.length")==min(count,5000)
    release_dom_cache(page)
    assert page.evaluate("!document.__stScrollCandidateCacheV1")


@pytest.mark.parametrize("viewport",[{"width":800,"height":600},{"width":390,"height":844}])
def test_mutation_and_fresh_geometry(page,viewport):
    page.set_viewport_size(viewport)
    page.route("https://example.com/fixture",lambda route:route.fulfill(body="<!doctype html>"))
    page.goto("https://example.com/fixture")
    page.set_content('''<!doctype html><style>body{margin:0;height:3000px;width:1800px}
      .panel{width:100px;height:100px;overflow:auto;direction:rtl}
      .panel div{width:500px;height:400px}</style>
      <div style="position:fixed;top:0">Fixed</div><div style="position:sticky;top:0">Sticky</div>
      <div class="panel"><div>Nested</div></div>
      <div id="moving" style="position:absolute;top:1800px">Moving</div>''')
    first=page.evaluate(SAMPLE)
    assert first["_performance"]["dom_cache_misses"]==1
    page.evaluate("""() => {
       document.querySelector('#moving').style.transform='translateY(-1750px)';
       const panel=document.querySelector('.panel');panel.scrollLeft=-40;panel.scrollTop=30;
    }""")
    changed=page.evaluate(SAMPLE)
    assert changed["_performance"]["dom_cache_hits"]==1
    assert len(changed["transforms"])>len(first["transforms"])
    assert any(c["rtl"] and c["x"]<0 and c["y"]==30 for c in changed["containers"])
    ids={n["id"] for n in changed["transforms"]}
    # Same-task mutation: takeRecords must invalidate before the callback.
    updated=page.evaluate("() => {document.body.prepend(document.createElement('h3'));return ("+SAMPLE+")()}")
    assert updated["_performance"]["dom_cache_invalidations"]==1
    assert ids.issubset({n["id"] for n in updated["transforms"]})
    page.evaluate("() => {document.body.append(document.body.firstChild);document.body.lastChild.remove()}")
    assert page.evaluate(SAMPLE)["_performance"]["dom_cache_misses"]==1
    page.evaluate("""() => {const b=document.createElement('body');b.innerHTML='<article>Hydrated</article>';
       document.documentElement.replaceChild(b,document.body)}""")
    assert page.evaluate(SNAPSHOT,True)["dom_count"]==1
    page.evaluate("() => {history.pushState({},'', '#spa');document.body.innerHTML='<p>SPA</p><p>Lazy</p>'}")
    state=page.evaluate(SNAPSHOT,True)
    assert state["dom_count"]==2
    assert state["_performance"]["dom_cache_misses"]==1
    release_dom_cache(page)
    page.goto("about:blank")
    assert page.evaluate(SAMPLE)["_performance"]["dom_cache_misses"]==1


def legacy_diff(previous,current):
    with Image.open(BytesIO(previous)) as a, Image.open(BytesIO(current)) as b:
        a,b=a.convert("RGB"),b.convert("RGB")
        r,g,blue=ImageChops.difference(a,b).split()
        mask=ImageChops.lighter(ImageChops.lighter(r,g),blue).point(lambda x:255 if x>12 else 0)
        percent=round(mask.histogram()[255]/(a.width*a.height)*100,4)
        background=b.convert("L").convert("RGB").point(lambda x:x//3)
        overlay=Image.composite(Image.new("RGB",b.size,(255,45,45)),background,mask)
        out=BytesIO()
        overlay.save(out,format="PNG")
        return percent,out.getvalue()


def pngs(mode,count):
    rng=Random(17)
    for _ in range(count):
        im=Image.frombytes("RGBA",(71,53),rng.randbytes(71*53*4)).convert(mode)
        with BytesIO() as out:
            im.save(out,format="PNG")
            yield out.getvalue()


def same_pixels(expected,actual):
    assert expected[0]==actual[0]
    with Image.open(BytesIO(expected[1])) as a, Image.open(BytesIO(actual[1])) as b:
        assert a.size==b.size and a.mode==b.mode=="RGB"
        assert a.tobytes()==b.tobytes()


@pytest.mark.parametrize("mode",["L","RGB","RGBA","P","1"])
def test_diff_equivalence_and_raw_png(mode,tmp_path):
    frames=list(pngs(mode,4))
    with PixelDiffSequence() as seq:
        assert seq.advance(frames[0])==(None,None)
        for i,(a,b) in enumerate(zip(frames,frames[1:])):
            expected=legacy_diff(a,b)
            same_pixels(expected,visual_diff(a,b))
            same_pixels(expected,seq.advance(b))
            path=tmp_path/("frame-%d.png"%i)
            meta=write_bytes(tmp_path,path.relative_to(tmp_path),b)
            assert path.read_bytes()==b
            assert meta["sha256"]==hashlib.sha256(b).hexdigest()
    assert seq.previous is None


def test_long_sequence_and_exception_cleanup():
    for _ in range(3):
        with pytest.raises(RuntimeError,match="cancel"):
            with PixelDiffSequence() as seq:
                previous=None
                for frame in pngs("RGB",150):
                    seq.advance(frame)
                    if previous is not None:
                        with pytest.raises(ValueError,match="closed image"):
                            previous.getpixel((0,0))
                    previous=seq.previous
                raise RuntimeError("cancel")
        assert seq.previous is None
        with pytest.raises(ValueError,match="closed image"):
            previous.getpixel((0,0))


def test_threshold_channels_and_size_mismatch():
    def encode(pixels):
        with Image.new("RGB",(len(pixels),1)) as image, BytesIO() as out:
            image.putdata(pixels)
            image.save(out,format="PNG")
            return out.getvalue()
    a=encode([(0,0,0)]*6)
    b=encode([(12,0,0),(13,0,0),(0,12,0),(0,13,0),(0,0,12),(0,0,13)])
    actual=visual_diff(a,b)
    same_pixels(legacy_diff(a,b),actual)
    assert actual[0]==50
    with pytest.raises(ValueError,match="dimensions changed"):
        visual_diff(a,encode([(0,0,0)]))


def test_observer_lifecycle_and_style_only_mutations(page):
    page.set_content('<div id="box" style="width:40px;height:40px">Text</div>')
    first=snapshot_scroll(page)
    page.evaluate("document.querySelector('#box').style.transform='translateX(10px)'")
    second=page.evaluate(SAMPLE)
    assert second["_performance"]["dom_cache_hits"]==1
    assert second["transforms"][0]["id"]==first["transforms"][0]["id"]
    assert second["transforms"][0]["transform"]!=first["transforms"][0]["transform"]
    for _ in range(10):
        release_dom_cache(page)
        assert page.evaluate("!document.__stScrollCandidateCacheV1")
        assert page.evaluate(SAMPLE)["_performance"]["dom_full_scans"]==1
    page.evaluate("document.querySelector('#box').remove()")
    assert page.evaluate(SAMPLE)["transforms"]==[]
