"""Fixed CSS-resolution profiles using isolated Chromium contexts, not real hardware."""
import hashlib
from pathlib import Path

from PIL import Image

from .browser import context_for, origin
from .measurements import measure
from .pipeline import CaptureCancelled

PROFILES = (
    ("iphone-13", "iPhone 13", 390, 844, 3, True, True),
    ("pixel-7", "Pixel 7", 412, 915, 2.625, True, True),
    ("ipad", "iPad", 768, 1024, 2, True, True),
    ("laptop", "Laptop", 1366, 768, 1, False, False),
    ("desktop", "Desktop", 1440, 900, 1, False, False),
    ("full-hd", "Full HD", 1920, 1080, 1, False, False),
)
LIMITATIONS = [
    "Chromium only, including Apple-shaped profiles; not Safari or physical devices.",
    "Fixed requested viewport and screen dimensions, not exact browser chrome or operating system behavior.",
    "Mobile user-agent strings are illustrative profiles; UA Client Hints and platform may differ.",
    "Screenshots use CSS pixel scale; device DPR still affects page rendering and media queries.",
    "Full-page screenshots are bounded to 8 million estimated CSS pixels; viewport fallback is explicit.",
    "Separate device evidence, not part of baseline comparison or explicit interaction scenario execution.",
]
MAX_PIXELS=8_000_000


def profiles():
    return [dict(id=i,label=label,width=w,height=h,dpr=dpr,is_mobile=mobile,has_touch=touch)
            for i,label,w,h,dpr,mobile,touch in PROFILES]


def device_options(profile, browser_version):
    width,height=profile["width"],profile["height"]
    options=dict(viewport={"width":width,"height":height},
                 screen={"width":width,"height":height},
                 device_scale_factor=profile["dpr"],is_mobile=profile["is_mobile"],
                 has_touch=profile["has_touch"])
    if profile["id"]=="iphone-13":
        options["user_agent"]="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    elif profile["id"]=="ipad":
        options["user_agent"]="Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    elif profile["id"]=="pixel-7":
        options["user_agent"]=f"Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser_version} Mobile Safari/537.36"
    return options


def planned_devices(url):
    return [dict(profile,url=url,status="not_attempted") for profile in profiles()]


def capture_device(browser, expected, root:Path, entry, cancelled=lambda:False):
    if cancelled():
        raise CaptureCancelled("Capture cancelled before device capture")
    result=dict(entry)
    context=None
    target=None
    try:
        options=device_options(entry,browser.version)
        context=context_for(browser,entry,expected,device_options=options)
        page=context.new_page()
        response=page.goto(entry["url"],wait_until="domcontentloaded",timeout=12000)
        if response is None or response.status>=400 or origin(page.url)!=expected:
            raise ValueError("Device page unavailable")
        page.wait_for_timeout(700)
        if origin(page.url)!=expected:
            raise ValueError("Device page changed origin")
        final_url=page.url
        if cancelled():
            raise CaptureCancelled("Capture cancelled before device screenshot")
        observed=page.evaluate("""() => ({
            inner_width:innerWidth,inner_height:innerHeight,screen_width:screen.width,screen_height:screen.height,
            dpr:devicePixelRatio,max_touch_points:navigator.maxTouchPoints,user_agent:navigator.userAgent,
            orientation:screen.orientation?.type ?? null,hover:matchMedia('(hover:hover)').matches,
            pointer_coarse:matchMedia('(pointer:coarse)').matches,
            document_width:Math.max(document.documentElement.scrollWidth,innerWidth),
            document_height:Math.max(document.documentElement.scrollHeight,innerHeight)
        })""")
        # Collect compact design evidence, not a duplicate full design report.
        snapshot=measure(page,measurements=True,interactions=False)
        from .advanced_design import summarize_advanced
        summary=summarize_advanced(snapshot["elements"])
        full=(observed["document_width"]<=4096 and observed["document_height"]<=16000
              and observed["document_width"]*observed["document_height"]<=MAX_PIXELS)
        slug=hashlib.sha256(entry["url"].encode()).hexdigest()[:16]
        relative=Path("devices")/entry["id"]/(slug+".png")
        target=root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(target),full_page=full,scale="css",animations="disabled",timeout=8000)
        if cancelled():
            raise CaptureCancelled("Capture cancelled after device screenshot")
        if page.url!=final_url:
            raise ValueError("Device page changed during capture")
        with Image.open(target) as img:
            if img.format!="PNG" or img.width*img.height>MAX_PIXELS:
                raise ValueError("Device image exceeds pixel budget")
            size=list(img.size)
        result.update(status="captured",path=relative.as_posix(),
                      sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      screenshot_mode="full_page" if full else "viewport",
                      image_size=size,observed=observed,design=summary,
                      media_queries=snapshot["media_queries"],limits=snapshot["limits"])
    except CaptureCancelled:
        if target is not None:
            target.unlink(missing_ok=True)
        raise
    except Exception:
        if target is not None:
            target.unlink(missing_ok=True)
        result.update(status="failed",reason="Device load, measurement or screenshot failed")
    finally:
        if context is not None:
            context.close()
    return result


def registry_entry(entry):
    """Keep large device design evidence out of PostgreSQL job progress."""
    return {k:v for k,v in entry.items() if k not in ("design","media_queries","limits")}
