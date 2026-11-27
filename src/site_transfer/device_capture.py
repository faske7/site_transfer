"""Fixed CSS-resolution profiles using isolated Chromium contexts, not real hardware."""
import hashlib
from pathlib import Path

from .browser import context_for, origin
from .measurements import measure
from .pipeline import CaptureCancelled
from .reliable_capture import capture_png, QualityFailure, DEVICE_TIMEOUT_MS
from .cookie_consent import handle_cookie_consent, consent_quality

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
    "Full-page screenshots are bounded to 8 million estimated CSS pixels; viewport fallback on size or screenshot timeout is explicit.",
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


def capture_device(browser, expected, root:Path, entry, cancelled=lambda:False, *, consent_config=None):
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
        final_url=page.url
        consent=handle_cookie_consent(page,expected,consent_config,cancelled)
        result['cookie_consent']=consent
        if consent['code']=='navigation_changed':
            raise ValueError('Cookie consent navigation rejected')
        if cancelled():
            raise CaptureCancelled("Capture cancelled before device screenshot")
        slug=hashlib.sha256(entry["url"].encode()).hexdigest()[:16]
        relative=Path("devices")/entry["id"]/(slug+".png")
        target=root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        quality=consent_quality(capture_png(page,target,expected,cancelled,DEVICE_TIMEOUT_MS,device=True),consent)
        result["quality"]=quality
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
        if cancelled():
            raise CaptureCancelled("Capture cancelled after device screenshot")
        if page.url!=final_url:
            raise ValueError("Device page changed during capture")
        result.update(status="captured",path=relative.as_posix(),
                      sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      screenshot_mode=quality["screenshot_mode"],
                      image_size=quality["image_size"],observed=observed,design=summary,
                      media_queries=snapshot["media_queries"],limits=snapshot["limits"])
    except CaptureCancelled:
        if target is not None:
            target.unlink(missing_ok=True)
        raise
    except QualityFailure as exc:
        if target is not None:
            target.unlink(missing_ok=True)
        result.update(status="failed",reason=str(exc),quality=exc.quality)
    except Exception as exc:
        if target is not None:
            target.unlink(missing_ok=True)
        code="capture_timeout" if type(exc).__name__=="TimeoutError" else "device_failed"
        result.update(status="failed",reason="Device load, measurement or screenshot failed",
                      quality=result.get("quality",{"status":"invalid","code":code}))
    finally:
        if context is not None:
            context.close()
    return result


def registry_entry(entry):
    """Keep large device design evidence out of PostgreSQL job progress."""
    return {k:v for k,v in entry.items() if k not in ("design","media_queries","limits")}
