"""Shared preparation, bounded retry and validated PNG publication."""
from time import monotonic

from .browser import origin
from .pipeline import CaptureCancelled
from .page_readiness import check_cancelled, remaining_ms, wait_ready
from .smart_scroll import smart_scroll
from .screenshot_quality import inspect_png

MAX_ATTEMPTS=2
DEVICE_TIMEOUT_MS=18000


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
        # Reserve at least half of each attempt (up to 5s) for the screenshot.
        # Retry uses short preparation, rather than repeating a full traversal.
        share=.7 if attempt==0 else 1.0
        start=monotonic()
        end=min(deadline,start+left*share/1000)
        reserve=min(5.0 if attempt==0 else 3.0,(end-start)*.5)
        prep_end=end-reserve
        diagnostic={"attempt":attempt+1,"budget_ms":remaining_ms(end)}
        phase="readiness"
        try:
            initial_limit=(4.0 if device else 3.0) if attempt==0 else .9
            diagnostic["readiness"]=wait_ready(page,min(prep_end,monotonic()+initial_limit),cancelled,
                                                min_ms=900 if attempt==0 else 300)
            phase="scroll"
            previous_scroll=attempts[-1].get("scroll",{}) if attempts else {}
            if attempt and previous_scroll.get("status")=="complete":
                diagnostic["scroll"]=dict(previous_scroll,reused=True)
            elif remaining_ms(prep_end) >= 600:
                diagnostic["scroll"]=smart_scroll(page,min(prep_end-.35,monotonic()+5.0),cancelled)
            else:
                diagnostic["scroll"]={"steps":0,"reached_bottom":False,"status":"bounded"}
            phase="post_scroll_readiness"
            diagnostic["post_scroll_readiness"]=wait_ready(page,min(prep_end,monotonic()+1.0),cancelled,min_ms=300)
            phase="geometry"
            check_cancelled(cancelled)
            if origin(page.url)!=expected or page.url!=final_url:
                raise QualityFailure({"status":"invalid","code":"navigation_changed"})
            dims=page.evaluate("""() => ({w:Math.max(document.documentElement.scrollWidth,innerWidth),
                h:Math.max(document.documentElement.scrollHeight,innerHeight),viewport_width:innerWidth})""")
            full=dims["w"]<=4096 and dims["h"]<=16000 and dims["w"]*dims["h"]<=limit
            if not full and not device:
                raise QualityFailure({"status":"invalid","code":"document_budget"})
            # If a full-page device screenshot itself timed out, the one retry
            # may capture the viewport. Never silently claim full-page evidence.
            fallback_reason=None
            if device and full and attempt and attempts[-1].get("failure_stage")=="screenshot" and attempts[-1]["quality"]["code"]=="capture_timeout":
                full=False
                fallback_reason="full_page_timeout"
            elif device and not full:
                fallback_reason="document_budget"
            diagnostic.update(document=dims,screenshot_mode="full_page" if full else "viewport",
                              screenshot_timeout_ms=remaining_ms(end))
            if fallback_reason:
                diagnostic["fallback_reason"]=fallback_reason
            phase="screenshot"
            if diagnostic["screenshot_timeout_ms"]<=0:
                phase="budget_before_screenshot"
                raise QualityFailure({"status":"invalid","code":"capture_timeout"})
            data=page.screenshot(full_page=full,scale="css",animations="disabled",timeout=diagnostic["screenshot_timeout_ms"])
            phase="validation"
            check_cancelled(cancelled)
            if page.url!=final_url:
                raise QualityFailure({"status":"invalid","code":"navigation_changed"})
            quality=inspect_png(data,limit)
            diagnostic.update(quality=quality,document=dims)
            diagnostic["elapsed_ms"]=int((monotonic()-start)*1000)
            if quality["status"]=="invalid":
                diagnostic["failure_stage"]="validation"
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
            if diagnostic["post_scroll_readiness"]["sample"].get("pending_images"):
                warnings.append("pending_visible_images")
            quality=dict(quality,status="warning" if warnings else "valid",warnings=warnings,
                         attempts=attempts+[diagnostic],screenshot_mode="full_page" if full else "viewport")
            check_cancelled(cancelled)
            # Do not create a registered image until validation has passed.
            phase="publication"
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
            diagnostic.update(quality=exc.quality,failure_stage=phase,
                              elapsed_ms=int((monotonic()-start)*1000))
            attempts.append(diagnostic)
            if exc.quality["code"] in ("navigation_changed","document_budget"):
                break
        except Exception as exc:
            diagnostic.update(quality={"status":"invalid","code":"capture_timeout" if type(exc).__name__=="TimeoutError" else "capture_failed"},
                              failure_stage=phase,elapsed_ms=int((monotonic()-start)*1000))
            attempts.append(diagnostic)
    last=attempts[-1]["quality"]["code"] if attempts else "capture_timeout"
    raise QualityFailure({"status":"invalid","code":last if last in ("navigation_changed","document_budget") else "retry_exhausted" if attempts else "capture_timeout",
                          "attempts":attempts})
