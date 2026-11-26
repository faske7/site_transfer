"""Bounded, observational readiness; never bypass network policy."""
from time import monotonic

from .pipeline import CaptureCancelled

SAMPLE = """() => {
 const d=document.documentElement,b=document.body;
 const imgs=Array.from(document.images).slice(0,500);
 const visible=imgs.filter(i=>{const r=i.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight});
 return {state:document.readyState,body:!!b,
   text:(b?.innerText||'').length,nodes:b?.getElementsByTagName('*').length||0,
   width:Math.max(d.scrollWidth,innerWidth),height:Math.max(d.scrollHeight,innerHeight),
   scrollable:Math.max(0,(document.scrollingElement||d).scrollHeight-innerHeight),
   fonts:!document.fonts||document.fonts.status==='loaded',
   pending_images:visible.filter(i=>!i.complete).length,
   broken_images:visible.filter(i=>i.complete&&!i.naturalWidth).length};
}"""


def check_cancelled(cancelled):
    if cancelled():
        raise CaptureCancelled("Capture cancelled during page preparation")


def remaining_ms(deadline):
    return max(0, int((deadline-monotonic())*1000))


def pause(page, deadline, cancelled, ms=150):
    check_cancelled(cancelled)
    left=remaining_ms(deadline)
    if left:
        page.wait_for_timeout(min(ms,left))
    check_cancelled(cancelled)


def wait_ready(page, deadline, cancelled, min_ms=900, min_scroll=0):
    """Poll observable signals, not networkidle or animation completion."""
    start=monotonic()
    previous=None
    stable=0
    latest={}
    while remaining_ms(deadline):
        check_cancelled(cancelled)
        latest=page.evaluate(SAMPLE)
        stable=stable+1 if latest==previous else 0
        previous=latest
        if (latest["body"] and latest["state"]=="complete" and latest["fonts"]
                and not latest["pending_images"] and latest["scrollable"]>=min_scroll and stable>=2
                and (monotonic()-start)*1000>=min_ms):
            return {"status":"settled","sample":latest}
        pause(page,deadline,cancelled)
    return {"status":"unsettled","sample":latest}
