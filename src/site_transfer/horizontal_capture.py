"""Conservative derived horizontal strip from already captured viewport PNGs.

No page mutation, extra screenshot, resizing or interpolation. Exact strips
require verified overlap; dynamic scenes also get a discrete frame overview.
"""
from contextlib import closing
from io import BytesIO
from time import monotonic
from urllib.parse import urlsplit

from PIL import Image, ImageChops

from .scroll_performance import DOM_CANDIDATES
from .page_readiness import check_cancelled

MAX_WIDTH = 16000
MAX_PIXELS = 8_000_000
MIN_OVERLAP = 32
MAX_OUTPUT_BYTES = 16 * 1024 * 1024

# Only direct clipping parents and pure horizontal translation. Reject
# ambiguous layouts rather than reconstructing or changing the reference.
PROBE = r"""
() => {""" + DOM_CANDIDATES + r"""
    window.__stHorizontalIds ??= new WeakMap();
    window.__stHorizontalCounter ??= 0;
    const integral=n=>Number.isFinite(n)&&Math.abs(n-Math.round(n))<0.001;
    let best=null, bestArea=0;
    for(const el of nodes){
        const r=rect(el);
        if(r.width<=innerWidth+32||r.bottom<=0||r.top>=innerHeight)continue;
        const parent=el.parentElement;
        if(!parent||parent===document.body||parent===document.documentElement)continue;
        const p=rect(parent);
        if(p.width<64||p.height<32||p.left<0||p.top<0||p.right>innerWidth||p.bottom>innerHeight)continue;
        if(r.left>p.left||r.right<p.right||r.top>p.top||r.bottom<p.bottom)continue;
        const ps=style(parent),s=style(el);
        if(!/^(hidden|clip|auto|scroll)$/.test(ps.overflowX)||
            ps.transform!=='none'||s.visibility!=='visible'||s.display==='none'||
            s.opacity!=='1'||(s.translate&&s.translate!=='none')||
            (s.rotate&&s.rotate!=='none')||(s.scale&&s.scale!=='none'))continue;
        // Exclude borders/padding: the clip must describe the actual pixels.
        if(parent.clientWidth!==p.width||parent.clientHeight!==p.height||
            ['paddingLeft','paddingRight','paddingTop','paddingBottom'].some(k=>parseFloat(ps[k])!==0))continue;
        let tx=0;
        if(s.transform!=='none'){
            const m=new DOMMatrixReadOnly(s.transform);
            if(!m.is2D||m.a!==1||m.b!==0||m.c!==0||m.d!==1||m.f!==0)continue;
            tx=m.e;
        }
        const values=[p.left,p.top,p.width,p.height,r.width,p.left-r.left,tx];
        if(!values.every(integral))continue;
        const [x,y,w,h,total,offset,translation]=values.map(Math.round);
        if(total<=w||offset<0||offset+w>total||total>16000||total*h>8000000)continue;
        if(w*h<=bestArea)continue;
        if(!window.__stHorizontalIds.has(el))window.__stHorizontalIds.set(el,++window.__stHorizontalCounter);
        best={id:window.__stHorizontalIds.get(el),clip:[x,y,w,h],total_width:total,
              offset,translation,scroll_y:window.scrollY,document_epoch:performance.timeOrigin};
        bestArea=w*h;
    }
    return {candidate:best,_performance:metrics};
}
"""


def eligible(url, viewport):
    return (urlsplit(url).path or "/")=="/" and viewport["name"] in (
        "desktop","desktop_wide") and viewport["width"]>=600


def _same_geometry(a,b):
    return (a["id"],a["clip"],a["total_width"],a["document_epoch"],a["offset"]+a["translation"]) == (b["id"],b["clip"],b["total_width"],b["document_epoch"],b["offset"]+b["translation"])


def _crop(root, frame, candidate):
    x,y,w,h=candidate["clip"]
    # Only read paths produced by the timeline, not page-controlled strings.
    with Image.open(root/frame["screenshot"]["path"]) as image:
        if image.format!="PNG" or min(x,y)<0 or x+w>image.width or y+h>image.height:
            raise ValueError("Invalid source crop")
        with closing(image.crop((x,y,x+w,y+h))) as crop:
            return crop.convert("RGB")


def build_panorama(root, frames, deadline, cancelled, byte_budget):
    """Return (report, PNG bytes or None); never change source frames."""
    groups={}
    for frame in frames:
        c=frame.get("horizontal_candidate")
        if c is not None:
            groups.setdefault((c["id"],tuple(c["clip"]),c["total_width"],c["document_epoch"],c["offset"]+c["translation"]),[]).append((frame,c))
    report={"status":"unavailable","reason":"no_verified_horizontal_strip"}
    if not groups:
        return report,None
    # One panorama per sequence. Prefer the group with the widest observed
    # offset range, without inventing any missing pixels.
    groups=sorted(groups.values(),key=lambda g:max(c["offset"] for _,c in g)-min(c["offset"] for _,c in g),reverse=True)
    for group in groups:
        check_cancelled(cancelled)
        if monotonic()>=deadline:
            return {"status":"unavailable","reason":"time_budget"},None
        first=group[0][1]
        x,y,w,h=first["clip"]
        total=first["total_width"]
        if not (0<w<total<=MAX_WIDTH and 0<h and total*h<=MAX_PIXELS):
            continue
        # Must actually observe horizontal transform change (not merely a
        # vertical page with a wide off-screen element).
        if len({c["translation"] for _,c in group})<2:
            continue
        ordered=sorted(group,key=lambda item:item[1]["offset"])
        if ordered[0][1]["offset"]!=0 or ordered[-1][1]["offset"]+w!=total:
            report={"status":"unavailable","reason":"incomplete_horizontal_coverage"}
            continue
        with Image.new("RGB",(total,h)) as canvas:
            end=0
            sources=[]
            rejected=False
            for frame,c in ordered:
                check_cancelled(cancelled)
                if monotonic()>=deadline:
                    return {"status":"unavailable","reason":"time_budget"},None
                offset=c["offset"]
                if offset<0 or offset+w>total or not _same_geometry(first,c):
                    rejected=True
                    break
                if offset+w<=end:
                    continue
                with closing(_crop(root,frame,c)) as tile:
                    if end:
                        overlap=end-offset
                        if overlap<MIN_OVERLAP:
                            rejected=True
                            break
                        with closing(canvas.crop((offset,0,end,h))) as a, closing(tile.crop((0,0,overlap,h))) as b:
                            with closing(ImageChops.difference(a,b)) as diff:
                                if diff.getbbox() or all(lo==hi for lo,hi in a.getextrema()):
                                    rejected=True
                                    break
                    canvas.paste(tile,(offset,0))
                    end=offset+w
                    sources.append({"index":frame["index"],"offset":offset,
                                    "sha256":frame["screenshot"]["sha256"]})
            if rejected or end!=total or len(sources)<2:
                report={"status":"unavailable","reason":"unverified_pixel_overlap"}
                continue
            with BytesIO() as out:
                canvas.save(out,format="PNG")
                data=out.getvalue()
            check_cancelled(cancelled)
            if monotonic()>=deadline:
                return {"status":"unavailable","reason":"time_budget"},None
            if len(data)>min(byte_budget,MAX_OUTPUT_BYTES):
                return {"status":"unavailable","reason":"byte_budget"},None
            return {"status":"derived","method":"exact_horizontal_overlap_v1",
                    "clip":first["clip"],"width":total,"height":h,"sources":sources},data
    return report,None


STORYBOARD_GAP = 8
STORYBOARD_MAX_FRAMES = 8


def _horizontal_signal(frame):
    observation=frame.get("scroll_observation") or {}
    if any(abs(c.get("dx",0))>2 for c in observation.get("coordinate_changes",[])):
        return True
    return any(abs(m["dx"])>2 and
               m["before"]["transform"]!=m["after"]["transform"]
               for m in frame.get("motion",[]))


def _sample_indices(indices, count):
    if len(indices)<=count:
        return indices
    return [indices[round(i*(len(indices)-1)/(count-1))] for i in range(count)]


def build_storyboard(root, frames, deadline, cancelled, byte_budget):
    """Chronological native-size viewport tiles, explicitly NOT a stitched panorama."""
    def unavailable(reason):
        return {"status":"unavailable","reason":reason},None

    if len(frames)<2:
        return unavailable("insufficient_frames")
    check_cancelled(cancelled)
    if monotonic()>=deadline:
        return unavailable("time_budget")
    if byte_budget<=0:
        return unavailable("byte_budget")
    with Image.open(root/frames[0]["screenshot"]["path"]) as first:
        w,h=first.size
    if not w or not h:
        return unavailable("invalid_frame")
    count=min(len(frames),STORYBOARD_MAX_FRAMES,
              (MAX_WIDTH+STORYBOARD_GAP)//(w+STORYBOARD_GAP),
              (MAX_PIXELS//h+STORYBOARD_GAP)//(w+STORYBOARD_GAP))
    if count<2:
        return unavailable("pixel_budget")
    active=set()
    last=None
    for i,frame in enumerate(frames):
        candidate=frame.get("horizontal_candidate")
        changed=bool(candidate and last and
                     candidate["id"]==last["id"] and candidate["offset"]!=last["offset"])
        if changed or _horizontal_signal(frame):
            active.update((max(0,i-1),i))
        last=candidate
    if active:
        indices=sorted(active)
        evidence="observed_horizontal_motion"
    else:
        # Preserve a useful overview even if bounded sampling could not
        # establish horizontal motion; never label it verified.
        indices=list(range(len(frames)))
        evidence="horizontal_motion_unverified"
    indices=_sample_indices(indices,count)
    width=len(indices)*w+(len(indices)-1)*STORYBOARD_GAP
    with Image.new("RGB",(width,h),(48,48,48)) as canvas:
        sources=[]
        for slot,i in enumerate(indices):
            check_cancelled(cancelled)
            if monotonic()>=deadline:
                return unavailable("time_budget")
            frame=frames[i]
            with Image.open(root/frame["screenshot"]["path"]) as image:
                if image.format!="PNG" or image.size!=(w,h):
                    return unavailable("viewport_dimensions_changed")
                with closing(image.convert("RGB")) as tile:
                    x=slot*(w+STORYBOARD_GAP)
                    canvas.paste(tile,(x,0))
            sources.append({"index":frame["index"],"sha256":frame["screenshot"]["sha256"],
                            "rect":[x,0,w,h]})
        with BytesIO() as out:
            canvas.save(out,format="PNG")
            data=out.getvalue()
    check_cancelled(cancelled)
    if monotonic()>=deadline:
        return unavailable("time_budget")
    if len(data)>min(byte_budget,MAX_OUTPUT_BYTES):
        return unavailable("byte_budget")
    return {"status":"derived","method":"chronological_viewport_storyboard_v1",
            "evidence":evidence,"width":width,"height":h,"gap":STORYBOARD_GAP,
            "sources":sources,"source_frame_count":len(frames),
            "omitted_from_overview":len(frames)-len(sources)},data
