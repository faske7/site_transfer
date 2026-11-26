"""Shared preparation, bounded retry and validated PNG publication."""
from time import monotonic

from .browser import origin
from .pipeline import CaptureCancelled
from .page_readiness import check_cancelled, remaining_ms, wait_ready
from .smart_scroll import smart_scroll
from .screenshot_quality import inspect_png

MAX_ATTEMPTS=2


class QualityFailure(ValueError):
    def __init__(self, quality):
        super().__init__("Screenshot evidence unavailable: "+quality["code"])
        self.quality=quality


def capture_png(page, target, expected, cancelled, timeout_ms, *, device=False):
    deadline=monotonic()+timeout_ms/1000
    attempts=[]
    limit=8_000_000 if device else 40_000_000
    final_url=page.url
    for attempt in range(MAX_ATTEMPTS):
        check_cancelled(cancelled)
        left=remaining_ms(deadline)
        if left<=0:
            break
        # Reserve part of the total budget for a retry. All waits share a deadline.
        share=.7 if attempt==0 else 1.0
        end=min(deadline,monotonic()+left*share/1000)
        prep_end=end-min(1.2,max(.1,(end-monotonic())*.3))
        diagnostic={"attempt":attempt+1}
        try:
            diagnostic["readiness"]=wait_ready(page,min(prep_end,monotonic()+2.0),cancelled)
            diagnostic["scroll"]=smart_scroll(page,min(prep_end-.35,monotonic()+3.5),cancelled)
            diagnostic["post_scroll_readiness"]=wait_ready(page,min(prep_end,monotonic()+1.0),cancelled,min_ms=300)
            check_cancelled(cancelled)
            if origin(page.url)!=expected or page.url!=final_url:
                raise QualityFailure({"status":"invalid","code":"navigation_changed"})
            dims=page.evaluate("""() => ({w:Math.max(document.documentElement.scrollWidth,innerWidth),
                h:Math.max(document.documentElement.scrollHeight,innerHeight),viewport_width:innerWidth})""")
            full=dims["w"]<=4096 and dims["h"]<=16000 and dims["w"]*dims["h"]<=limit
            if not full and not device:
                raise QualityFailure({"status":"invalid","code":"document_budget"})
            if remaining_ms(end)<=0:
                raise QualityFailure({"status":"invalid","code":"capture_timeout"})
            data=page.screenshot(full_page=full,scale="css",animations="disabled",timeout=remaining_ms(end))
            check_cancelled(cancelled)
            if page.url!=final_url:
                raise QualityFailure({"status":"invalid","code":"navigation_changed"})
            quality=inspect_png(data,limit)
            diagnostic.update(quality=quality,document=dims)
            if quality["status"]=="invalid":
                attempts.append(diagnostic)
                continue
            warnings=[]
            if quality["status"]=="warning":
                warnings.append(quality["code"])
            if dims["w"]>dims["viewport_width"]:
                warnings.append("document_overflow")
            if diagnostic["scroll"]["status"]!="complete":
                warnings.append("scroll_bounded")
            if diagnostic["readiness"]["status"]!="settled" or diagnostic["post_scroll_readiness"]["status"]!="settled":
                warnings.append("readiness_unsettled")
            if diagnostic["post_scroll_readiness"]["sample"].get("broken_images"):
                warnings.append("broken_visible_images")
            if device and not full:
                warnings.append("viewport_fallback")
            quality=dict(quality,status="warning" if warnings else "valid",warnings=warnings,
                         attempts=attempts+[diagnostic],screenshot_mode="full_page" if full else "viewport")
            check_cancelled(cancelled)
            # Do not create a registered image until validation has passed.
            temp=target.with_suffix(".pending")
            try:
                temp.write_bytes(data)
                check_cancelled(cancelled)
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
            return quality
        except CaptureCancelled:
            raise
        except QualityFailure as exc:
            diagnostic["quality"]=exc.quality
            attempts.append(diagnostic)
            if exc.quality["code"] in ("navigation_changed","document_budget"):
                break
        except Exception as exc:
            diagnostic["quality"]={"status":"invalid","code":"capture_timeout" if type(exc).__name__=="TimeoutError" else "capture_failed"}
            attempts.append(diagnostic)
    last=attempts[-1]["quality"]["code"] if attempts else "capture_timeout"
    raise QualityFailure({"status":"invalid","code":last if last in ("navigation_changed","document_budget") else "retry_exhausted" if attempts else "capture_timeout",
                          "attempts":attempts})
