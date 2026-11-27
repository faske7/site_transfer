"""Horizontal homepage evidence: exact strips and honest dynamic overviews."""
import hashlib
from io import BytesIO
from time import monotonic

import pytest
from PIL import Image, ImageDraw

from site_transfer.horizontal_capture import (
    PROBE, eligible, build_panorama, build_storyboard, STORYBOARD_GAP,
)
from site_transfer.pipeline import CaptureCancelled
from site_transfer.scroll_timeline import sequence_prefix, write_bytes
from site_transfer.manifest import timeline_files

URL="https://example.com/"


def png(image):
    with BytesIO() as out:
        image.save(out,format="PNG")
        return out.getvalue()


def fixture_frames(root,dynamic=False):
    prefix=sequence_prefix(URL,"desktop")
    frames=[]
    with Image.new("RGB",(192,64)) as scene:
        for x in range(192):
            ImageDraw.Draw(scene).line((x,0,x,63),fill=(x,(x*7)%256,255-x))
        expected=png(scene)
        for index,offset in enumerate([0,64,96]):
            with scene.crop((offset,0,offset+96,64)) as tile:
                if dynamic and index:
                    ImageDraw.Draw(tile).rectangle((0,0,20,20),fill="red")
                data=png(tile)
            frame={"index":index,"quality":{"status":"valid"},
                   "screenshot":write_bytes(root,prefix/f"frame-{index:03d}.png",data),
                   "horizontal_candidate":{"id":1,"clip":[0,0,96,64],"total_width":192,
                       "offset":offset,"translation":-offset,"document_epoch":1,"scroll_y":index*100}}
            if index:
                frame["difference_map"]=write_bytes(root,prefix/f"diff-{index:03d}.png",data)
            frames.append(frame)
    return frames,expected


def decode(data):
    with Image.open(BytesIO(data)) as image:
        return image.size,image.tobytes()


def test_exact_panorama(tmp_path):
    frames,expected=fixture_frames(tmp_path)
    report,data=build_panorama(tmp_path,frames,monotonic()+10,lambda:False,10**6)
    assert report["status"]=="derived"
    assert report["method"]=="exact_horizontal_overlap_v1"
    assert decode(data)==decode(expected)
    assert [f["index"] for f in report["sources"]]==[0,1,2]
    for frame in frames:
        assert hashlib.sha256((tmp_path/frame["screenshot"]["path"]).read_bytes()).hexdigest()==frame["screenshot"]["sha256"]


def test_dynamic_storyboard_keeps_pixels(tmp_path):
    frames,_=fixture_frames(tmp_path,dynamic=True)
    report,data=build_panorama(tmp_path,frames,monotonic()+10,lambda:False,10**6)
    assert data is None
    assert report["reason"]=="unverified_pixel_overlap"
    report,data=build_storyboard(tmp_path,frames,monotonic()+10,lambda:False,10**6)
    assert report["status"]=="derived"
    assert report["evidence"]=="observed_horizontal_motion"
    assert report["width"]==96*3+2*STORYBOARD_GAP
    with Image.open(BytesIO(data)) as overview:
        for source in report["sources"]:
            x,y,w,h=source["rect"]
            frame=frames[source["index"]]
            with Image.open(tmp_path/frame["screenshot"]["path"]) as original:
                assert overview.crop((x,y,x+w,y+h)).tobytes()==original.tobytes()


def test_partial_coverage_and_unverified_storyboard(tmp_path):
    frames,_=fixture_frames(tmp_path)
    report,data=build_panorama(tmp_path,frames[:2],monotonic()+10,lambda:False,10**6)
    assert data is None and report["reason"]=="incomplete_horizontal_coverage"
    for frame in frames:
        del frame["horizontal_candidate"]
    report,data=build_storyboard(tmp_path,frames,monotonic()+10,lambda:False,10**6)
    assert data and report["evidence"]=="horizontal_motion_unverified"


@pytest.mark.parametrize("builder",[build_panorama,build_storyboard])
def test_budgets_and_cancellation(tmp_path,builder):
    frames,_=fixture_frames(tmp_path)
    assert builder(tmp_path,frames,monotonic()-1,lambda:False,10**6)[1] is None
    assert builder(tmp_path,frames,monotonic()+10,lambda:False,1)[1] is None
    with pytest.raises(CaptureCancelled):
        builder(tmp_path,frames,monotonic()+10,lambda:True,10**6)


@pytest.mark.parametrize("url,name,width,result",[
    (URL,"desktop",1280,True),(URL,"desktop_wide",1920,True),
    (URL,"mobile",390,False),(URL+"catalog","desktop",1280,False),
    (URL,"desktop",390,False)])
def test_scope(url,name,width,result):
    assert eligible(url,{"name":name,"width":width}) is result


def test_manifest_provenance(tmp_path):
    frames,_=fixture_frames(tmp_path)
    prefix=sequence_prefix(URL,"desktop")
    sequence={"url":URL,"viewport":"desktop","status":"captured","frames":frames}
    for key,builder,filename in [
        ("horizontal_panorama",build_panorama,"horizontal-panorama.png"),
        ("horizontal_storyboard",build_storyboard,"horizontal-storyboard.png")]:
        report,data=builder(tmp_path,frames,monotonic()+10,lambda:False,10**6)
        report["image"]=write_bytes(tmp_path,prefix/filename,data)
        sequence[key]=report
    manifest={"scroll_timeline_manifest":"scroll-timeline-manifest.json",
              "scroll_timeline_sha256":"a"*64,"scroll_timeline":[sequence]}
    files=timeline_files(manifest)
    assert str(prefix/"horizontal-panorama.png") in files
    assert str(prefix/"horizontal-storyboard.png") in files
    sequence["horizontal_storyboard"]["sources"][0]["sha256"]="b"*64
    with pytest.raises(ValueError,match="provenance"):
        timeline_files(manifest)


def test_browser_probe():
    pw=pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            browser=p.chromium.launch(headless=True)
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Chromium not installed")
            raise
        try:
            page=browser.new_page(viewport={"width":800,"height":600})
            page.set_content("""<!doctype html><style>body{margin:0}
                #clip{position:fixed;left:0;top:0;width:800px;height:300px;overflow:hidden}
                #strip{width:1600px;height:300px;background:linear-gradient(90deg,red,blue)}
                </style><div id="clip"><div id="strip"></div></div>""")
            first=page.evaluate(PROBE)["candidate"]
            assert first and first["offset"]==0
            page.evaluate("document.querySelector('#strip').style.transform='translateX(-800px)'")
            after=page.evaluate(PROBE)["candidate"]
            assert after["id"]==first["id"] and after["offset"]==800
            assert after["translation"]==-800
        finally:
            browser.close()
