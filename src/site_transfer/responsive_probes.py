"""Bounded width-only observations on the already loaded desktop page."""
from .pipeline import CaptureCancelled

WIDTHS=(390,768,1024,1440,1920)
MAX_ROUTES=10
MAX_TARGETS=24
LIMITATIONS=[
    "Resizing an existing desktop context, not mobile device emulation or fresh page loads",
    "Offline after baseline; resize-dependent network resources may be incomplete",
    "Only sampled positional selectors and accessible declared media queries; no inferred breakpoint",
    "Observations are sequential and may reflect resize-driven JavaScript state",
]

PROBE_JS=r"""
(args)=>{
  const round=n=>Math.round(n*100)/100;
  const targets=args.selectors.map(selector=>{
    const matches=document.querySelectorAll(selector);
    if(matches.length!==1)return {selector,status:'missing_or_ambiguous'};
    const el=matches[0], b=el.getBoundingClientRect(), s=getComputedStyle(el);
    return {selector,status:'observed',visible:b.width>0&&b.height>0&&s.display!=='none'&&s.visibility==='visible'&&s.opacity!=='0',
      rect:{x:round(b.x+scrollX),y:round(b.y+scrollY),width:round(b.width),height:round(b.height)},
      display:s.display,position:s.position,grid_columns:s.gridTemplateColumns,flex_direction:s.flexDirection,
      font_size:s.fontSize,gap:s.gap};
  });
  return {inner_width:innerWidth,inner_height:innerHeight,document_width:document.documentElement.scrollWidth,
    document_height:document.documentElement.scrollHeight,media_queries:args.conditions.map(condition=>({condition,matches:matchMedia(condition).matches})),targets};
}
"""


def probe_widths(page, snapshot, cancelled=lambda:False):
    selectors=[]
    for row in snapshot["elements"]:
        if row.get("tag") in ("html","body","main","header","nav","aside","footer","h1","h2") or row.get("style",{}).get("display") in ("grid","inline-grid","flex","inline-flex"):
            if row["selector"] not in selectors:
                selectors.append(row["selector"])
            if len(selectors)>=MAX_TARGETS:
                break
    conditions=list(dict.fromkeys(q["condition"] for q in snapshot["media_queries"]
                                  if isinstance(q.get("condition"),str) and len(q["condition"])<240))[:100]
    original=page.viewport_size
    url=page.url
    observations=[]
    # This context will be closed after the report; no baseline or state image is taken after resize.
    page.context.set_offline(True)
    page.mouse.move(0,0)
    for width in WIDTHS:
        if cancelled():
            raise CaptureCancelled("Capture cancelled at responsive probe boundary")
        try:
            page.set_viewport_size({"width":width,"height":original["height"]})
            page.wait_for_timeout(150)
            if page.url!=url:
                raise ValueError("Page navigated")
            result=page.evaluate(PROBE_JS,{"selectors":selectors,"conditions":conditions})
            if page.url!=url:
                raise ValueError("Page navigated")
            observations.append({"requested_width":width,"status":"observed",**result})
        except Exception:
            observations.append({"requested_width":width,"status":"failed","reason":"Resize or measurement unavailable"})
            if page.url!=url:
                break
    attempted={row["requested_width"] for row in observations}
    observations.extend({"requested_width":w,"status":"not_attempted","reason":"Page navigated"} for w in WIDTHS if w not in attempted)
    return {"status":"observed" if all(row["status"]=="observed" for row in observations) else "partial",
            "observations":observations,"limitations":LIMITATIONS}
