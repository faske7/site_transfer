"""Bounded, observational readiness; never bypass network policy."""
from time import monotonic

from .pipeline import CaptureCancelled

SAMPLE = """() => {
 const d=document.documentElement,b=document.body;
 const imgs=Array.from(document.images).slice(0,500);
 const visible=imgs.filter(i=>{const r=i.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight});
 const text=(b?.innerText||'').trim().length;
 const elements=b?.getElementsByTagName('*');
 // A stable script-only shell is not a ready page. Text-free visual pages
 // can still settle using bounded image / painted-element hints.
 let visual_hint=visible.some(i=>i.complete&&i.naturalWidth>0);
 if (!text&&!visual_hint&&elements) {
   for(let i=0;i<Math.min(elements.length,80);i++){
     const el=elements[i];
     if(el.matches('script,style,template,link,meta,noscript')) continue;
     const r=el.getBoundingClientRect();
     if(r.width<=0||r.height<=0||r.bottom<=0||r.top>=innerHeight) continue;
     const s=getComputedStyle(el);
     if(s.visibility!=='visible'||Number(s.opacity)===0) continue;
     if(el.matches('svg,canvas,video')||s.backgroundImage!=='none'||
        !['rgba(0, 0, 0, 0)','rgb(255, 255, 255)'].includes(s.backgroundColor)){
       visual_hint=true;
       break;
     }
   }
 }
 return {state:document.readyState,body:!!b,
   text,nodes:elements?.length||0,visual_hint,
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
        if (latest["body"] and (latest["text"] or latest["visual_hint"])
                and latest["state"]=="complete" and latest["fonts"]
                and not latest["pending_images"] and latest["scrollable"]>=min_scroll and stable>=2
                and (monotonic()-start)*1000>=min_ms):
            return {"status":"settled","sample":latest}
        pause(page,deadline,cancelled)
    return {"status":"unsettled","sample":latest}
