import json
from importlib.resources import files
from pathlib import Path

import pytest

from site_transfer.advanced_design import pixels, milliseconds, rgba, summarize_advanced
from site_transfer.design_report import build_report
from site_transfer.design_tokens import summarize
from site_transfer.responsive_probes import probe_widths
from site_transfer.pipeline import CaptureCancelled


@pytest.mark.parametrize("value,expected",[("12.5px",12.5),("-2px",-2),("normal",None),("1rem",None),("8px 4px",None)])
def test_pixels(value,expected):
    assert pixels(value)==expected


@pytest.mark.parametrize("value,expected",[("0.2s",200),("150ms",150),("-0.1s",-100),("auto",None)])
def test_time(value,expected):
    assert milliseconds(value)==expected


@pytest.mark.parametrize("value,expected",[("rgb(1, 2, 3)",("#010203",1.0)),("rgba(0, 10, 255, 0.5)",("#000aff",0.5)),("color(display-p3 1 0 0)",None)])
def test_colors(value,expected):
    assert rgba(value)==expected


def test_report_schema_parity():
    public=Path(__file__).resolve().parents[1]/"schemas/design-report.schema.json"
    assert public.read_bytes()==files("site_transfer").joinpath("resources","design-report.schema.json").read_bytes()


def test_sampled_counts():
    result=summarize_advanced([{"style":{"font-size":"16px","gap":"8px","color":"rgb(1, 2, 3)","transition-duration":"0.2s, 150ms"}}]*2)
    assert result["typography_px"]["font-size"]==[{"value":16,"count":2}]
    assert result["spacing_px"]["gap"]==[{"value":8,"count":2}]
    assert result["palette"]==[{"hex":"#010203","alpha":1,"count":2}]
    assert result["motion_ms"]["transition-duration"]==[{"value":150,"count":2},{"value":200,"count":2}]


def test_known_browser_design():
    pw=pytest.importorskip("playwright.sync_api")
    from site_transfer.measurements import measure
    with pw.sync_playwright() as playwright:
        try:
            browser=playwright.chromium.launch(headless=True)
        except pw.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Chromium not installed")
            raise
        try:
            page=browser.new_page(viewport={"width":1440,"height":900})
            page.set_content("""<style>body{margin:0;color:rgb(1,2,3);font:16px Arial}
            main{display:grid;grid-template-columns:1fr 1fr;gap:24px}
            h1{font-size:32px;line-height:40px} button{transition:color .2s}
            @media(max-width:768px){main{grid-template-columns:1fr;gap:8px}}
            </style><main><h1>Heading</h1><button aria-label="Menu">Menu</button><img width="20" height="20"></main>""")
            snapshot=measure(page)
            summary=summarize(snapshot)
            advanced=summary["advanced"]
            assert advanced["headings"][0]["font_size"]=="32px"
            assert advanced["accessibility"]["sampled_images_without_alt_attribute"]==1
            assert any(c["gap"]=="24px" for c in advanced["containers"])
            assert {"value":200,"count":1} in advanced["motion_ms"]["transition-duration"]
            assert any(c["hex"]=="#010203" for c in advanced["palette"])
            with pytest.raises(CaptureCancelled):
                probe_widths(page,snapshot,lambda:True)
            probes=probe_widths(page,snapshot)
            assert probes["status"]=="observed"
            assert [p["requested_width"] for p in probes["observations"]]==[390,768,1024,1440,1920]
            for result in probes["observations"]:
                assert result["inner_width"]==result["requested_width"]
                main=next(t for t in result["targets"] if t["selector"].endswith("main:nth-of-type(1)"))
                assert main["gap"]==("8px" if result["requested_width"]<=768 else "24px")
                assert result["media_queries"][0]["matches"]==(result["requested_width"]<=768)
            boundary=probes["declared_breakpoints"][0]
            assert boundary["width"]==768
            assert [r["requested_width"] for r in boundary["samples"]]==[767,768,769]
            assert [r["media_queries"][0]["matches"] for r in boundary["samples"]]==[True,True,False]
            assert any("gap" in row["changed_properties"] for row in boundary["changed_targets"])
            report=build_report("https://example.com/","desktop","screenshots/desktop/test.png",snapshot,summary,None,probes)
            assert json.loads(json.dumps(report))==report
        finally:
            browser.close()
