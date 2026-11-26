"""Bounded width-only observations on the already loaded desktop page."""
import re
from .pipeline import CaptureCancelled

WIDTHS=(390,768,1024,1440,1920)
MAX_ROUTES=10
MAX_TARGETS=24
MAX_BREAKPOINTS=4
SIMPLE_WIDTH = re.compile(r"\(\s*(min|max)-width\s*:\s*(\d{1,4})px\s*\)", re.I)
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


def declared_boundaries(conditions):
    """Only exact simple integer px min/max-width conditions, never inferred."""
    found={}
    for condition in conditions:
        match=SIMPLE_WIDTH.fullmatch(condition)
        if match and 241<=int(match[2])<=2559:
            found.setdefault(int(match[2]),[]).append(condition)
    return [{"width":width,"conditions":found[width]} for width in sorted(found)[:MAX_BREAKPOINTS]]


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
    boundaries=declared_boundaries(conditions)
    requested=list(dict.fromkeys([*WIDTHS,*(w for b in boundaries for w in (b["width"]-1,b["width"],b["width"]+1))]))
    for width in requested:
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
    attempted={row["requested_width"]:row for row in observations}
    for w in requested:
        attempted.setdefault(w,{"requested_width":w,"status":"not_attempted","reason":"Page navigated"})
    boundary_results=[]
    for boundary in boundaries:
        width=boundary["width"]
        samples=[attempted[w] for w in (width-1,width,width+1)]
        changes=[]
        if all(s["status"]=="observed" for s in samples):
            before,after=samples[0],samples[-1]
            left={t["selector"]:t for t in before["targets"]}
            right={t["selector"]:t for t in after["targets"]}
            for selector in sorted(left.keys() & right.keys()):
                x,y=left[selector],right[selector]
                keys=[k for k in ("visible","display","position","grid_columns","flex_direction","font_size","gap") if x.get(k)!=y.get(k)]
                if keys:
                    changes.append({"selector":selector,"changed_properties":keys})
        boundary_results.append({**boundary,"samples":samples,"changed_targets":changes})
    return {"status":"observed" if all(row["status"]=="observed" for row in attempted.values()) else "partial",
            "observations":[attempted[w] for w in WIDTHS],"declared_breakpoints":boundary_results,
            "limitations":LIMITATIONS+["At most four simple declared integer px boundaries; other media conditions are not inferred"]}
