from site_transfer.colors import colors
from site_transfer.design_tokens import aggregate, summarize
from site_transfer.motion import motion
from site_transfer.responsive import responsive
from site_transfer.typography import typography


def snapshot():
    return {"elements": [
        {"style": {"font-family": "Arial", "font-size": "16px", "color": "rgb(0, 0, 0)",
                   "gap": "8px", "transition-duration": "0.2s", "animation-name": "none"}},
        {"style": {"font-family": "Arial", "font-size": "20px", "color": "rgb(0, 0, 0)"}},
        {"style": {"font-family": "Inter", "font-size": "16px"}},
    ], "viewport": {"width": 390, "height": 844}, "media_queries": [{"condition": "(max-width: 600px)", "matches": True}],
        "animations": [], "keyframes": [], "limits": {"dom_truncated": False}}


def test_typography_observed_counts():
    assert typography(snapshot()["elements"])["font-family"][0] == {"value": "Arial", "count": 2}


def test_colors_ignore_missing():
    assert colors(snapshot()["elements"])["color"] == [{"value": "rgb(0, 0, 0)", "count": 2}]


def test_motion_declared_not_observed():
    result = motion(snapshot())
    assert result["observed"] == []
    assert result["declared"]["transition-duration"] == [{"value": "0.2s", "count": 1}]


def test_aggregate_and_responsive():
    summary = summarize(snapshot())
    entries = [{"url":"https://example.com/", "viewport": name, "summary":summary} for name in ["desktop","mobile"]]
    assert len(responsive(entries)[0]["observations"]) == 2
    result = aggregate(entries)
    assert result["reports"] == 2
    assert result["tokens"]["typography"]["font-family"][0]["count"] == 4


def test_empty_aggregate():
    assert aggregate([])["reports"] == 0
    assert aggregate([])["tokens"] == {}


def test_no_fake_breakpoints():
    data = snapshot()
    data["media_queries"] = []
    result = aggregate([{"url":"https://example.com/", "viewport":"mobile", "summary":summarize(data)}])
    assert result["responsive"][0]["observations"][0]["media_queries"] == []


def test_mobile_hover_is_not_attempted():
    from site_transfer.interactions import inspect_interactions
    data = {"candidates": [], "viewport": {"hover": False}}
    assert inspect_interactions(None, data)["hover"] == []


def test_browser_fixture():
    import pytest
    playwright = pytest.importorskip("playwright.sync_api")
    from site_transfer.measurements import measure
    with playwright.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except playwright.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Chromium not installed")
            raise
        try:
            page = browser.new_page(viewport={"width":390,"height":844})
            page.set_content("<style>body{font-family:Arial;color:rgb(1,2,3)} @media(max-width:600px){button{padding:8px}} @keyframes fade{from{opacity:0}to{opacity:1}}</style><button>Menu</button>")
            data = measure(page)
            assert any(row["tag"] == "button" and row["style"]["padding-top"] == "8px" for row in data["elements"])
            assert any(query["matches"] for query in data["media_queries"])
            assert any(k["name"] == "fade" for k in data["keyframes"])
            assert data["candidates"]
        finally:
            browser.close()
