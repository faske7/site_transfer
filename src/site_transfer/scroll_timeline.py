"""Opt-in ordered viewport evidence; independent fresh context per sequence."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from time import monotonic

from PIL import Image, ImageChops
from .browser import context_for
from .cookie_consent import handle_cookie_consent
from .page_readiness import check_cancelled, remaining_ms, pause, wait_ready
from .pipeline import CaptureCancelled
from .screenshot_quality import inspect_png

MAX_SEQUENCE_BYTES = 96 * 1024 * 1024
PIXEL_THRESHOLD = 12
LIMITATIONS = [
    "Viewport pixel difference includes ordinary scrolling, carousels and animation.",
    "DOM signature is sampled; not a complete DOM diff.",
    "Motion uses sampled visible nodes and scroll-adjusted geometry; not causal animation inference.",
    "Bottom and geometry/DOM stability are observational, not proof of complete lazy loading.",
    "No arbitrary drag or scripted user actions; mobile may use scrollBy fallback.",
    "Continuously moving visuals do not prevent bottom completion.",
]

SNAPSHOT = r"""
(track) => {
    const doc=document.scrollingElement;
    const nodes=document.body.querySelectorAll('*');
    const limit=Math.min(nodes.length,5000);
    window.__stTimelineIds ??= new WeakMap();
    window.__stTimelineCounter ??= 0;
    const tags=[],elements=[];
    for(let i=0;i<limit;i++){
        const el=nodes[i];
        tags.push(el.tagName);
        if(!track||elements.length>=500)continue;
        const r=el.getBoundingClientRect();
        if(r.width<1||r.height<1||r.bottom<=0||r.top>=innerHeight||r.right<=0||r.left>=innerWidth)continue;
        const s=getComputedStyle(el);
        if(s.visibility==='hidden'||s.display==='none')continue;
        if(!window.__stTimelineIds.has(el))window.__stTimelineIds.set(el,++window.__stTimelineCounter);
        const round=n=>Math.round(n*10)/10;
        elements.push({id:window.__stTimelineIds.get(el),tag:el.tagName,
          class:(el.getAttribute('class')||'').slice(0,160),
          x:round(r.x),y:round(r.y),width:round(r.width),height:round(r.height),
          transform:s.transform,opacity:s.opacity,position:s.position});
    }
    return {scroll_y:Math.round(doc.scrollTop),document_height:doc.scrollHeight,
      viewport_height:innerHeight,max_scroll:Math.max(0,doc.scrollHeight-innerHeight),
      dom_count:nodes.length,tags,text:(document.body.innerText||'').slice(0,100000),
      visible_elements:elements,dom_sample_truncated:nodes.length>limit,
      motion_sample_truncated:track&&elements.length>=500};
}
"""


def snapshot(page, track):
    state=page.evaluate(SNAPSHOT,track)
    signature=json.dumps([state.pop("tags"),state.pop("text")],ensure_ascii=False)
    state["dom_hash"]=hashlib.sha256(signature.encode()).hexdigest()
    return state


def visual_diff(previous, current):
    with Image.open(BytesIO(previous)) as a, Image.open(BytesIO(current)) as b:
        a,b=a.convert("RGB"),b.convert("RGB")
        if a.size!=b.size:
            raise ValueError("Timeline viewport dimensions changed")
        r,g,blue=ImageChops.difference(a,b).split()
        mask=ImageChops.lighter(ImageChops.lighter(r,g),blue).point(
            lambda x:255 if x>PIXEL_THRESHOLD else 0)
        percent=round(mask.histogram()[255]/(a.width*a.height)*100,4)
        background=b.convert("L").convert("RGB").point(lambda x:x//3)
        overlay=Image.composite(Image.new("RGB",b.size,(255,45,45)),background,mask)
        output=BytesIO()
        overlay.save(output,format="PNG")
        return percent,output.getvalue()


def compare_motion(previous,current):
    if previous is None:
        return []
    old={el["id"]:el for el in previous["visible_elements"]}
    delta=current["scroll_y"]-previous["scroll_y"]
    result=[]
    for el in current["visible_elements"]:
        before=old.get(el["id"])
        if before is None:
            continue
        dx=el["x"]-before["x"]
        dy=el["y"]-before["y"]+(0 if el["position"]=="fixed" else delta)
        if (abs(dx)>2 or abs(dy)>2 or abs(el["width"]-before["width"])>2 or
            abs(el["height"]-before["height"])>2 or
            el["transform"]!=before["transform"] or el["opacity"]!=before["opacity"]):
            result.append({"id":el["id"],"dx":round(dx,2),"dy_adjusted":round(dy,2),
                           "before":before,"after":el})
    return result


def sequence_prefix(url,viewport):
    return Path("scroll-timeline")/viewport/hashlib.sha256(url.encode()).hexdigest()[:16]


def write_bytes(root, relative, data):
    target=root/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix(".pending")
    try:
        temp.write_bytes(data)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return {"path":relative.as_posix(),"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}


def capture_timeline(browser,viewport,expected,root,url,options,profile,consent_config,
                     cancelled=lambda:False,checkpoint=lambda entry:None):
    start=monotonic()
    deadline=start+options.get("timeout_ms",300000)/1000
    prefix=sequence_prefix(url,viewport["name"])
    mobile=viewport["width"]<600
    step=profile.get("step_px",600 if mobile else 250)
    settle=profile.get("settle_ms",800 if mobile else 1500)
    track=profile.get("motion_tracking",not mobile)
    threshold=options.get("visual_threshold_percent",0.5)
    stable_limit=options.get("stable_steps",5)
    entry={"url":url,"viewport":viewport["name"],"status":"not_attempted",
           "step_px":step,"settle_ms":settle,"motion_tracking":track,
           "visual_threshold_percent":threshold,"pixel_threshold":PIXEL_THRESHOLD,
           "stable_steps":stable_limit,"frames":[],"stop_reason":"not_attempted"}
    context=None
    previous=previous_bytes=None
    stable=0
    total_bytes=0
    fallback=False
    popups=[]
    navigations=[]
    try:
        check_cancelled(cancelled)
        context=context_for(browser,viewport,expected)
        page=context.new_page()
        def close_popup(popup):
            popups.append(True)
            popup.close()
        page.on("popup",close_popup)
        response=page.goto(url,wait_until="domcontentloaded",timeout=min(30000,remaining_ms(deadline)))
        if response is None or response.status>=400 or page.url!=url or popups:
            entry["stop_reason"]="initial_load_failed"
            return entry
        consent=handle_cookie_consent(page,expected,consent_config,cancelled)
        entry["cookie_consent"]=consent
        if consent["status"] in ("failed","unresolved") or page.url!=url or popups:
            entry["stop_reason"]="cookie_consent_unresolved"
            return entry
        # Only read-only scroll actions after preflight; do not relax the
        # public GET/HEAD network guard. Lazy-loaded content needs networking.
        def on_navigation(frame):
            if frame==page.main_frame and frame.url!=url:
                navigations.append(True)
        page.on("framenavigated",on_navigation)
        wait_ready(page,min(deadline,monotonic()+4),cancelled)
        page.evaluate("window.scrollTo(0,0)")
        pause(page,deadline,cancelled,settle)
        entry["stop_reason"]="max_frames"
        for index in range(options.get("max_frames",150)):
            check_cancelled(cancelled)
            if remaining_ms(deadline)<=0:
                entry["stop_reason"]="time_budget"
                break
            if page.url!=url or navigations or popups:
                entry["stop_reason"]="navigation_changed"
                break
            state=snapshot(page,track)
            left=remaining_ms(deadline)
            if left<=0:
                entry["stop_reason"]="time_budget"
                break
            data=page.screenshot(full_page=False,animations="allow",scale="css",timeout=min(15000,left))
            check_cancelled(cancelled)
            if page.url!=url or navigations or popups:
                entry["stop_reason"]="navigation_changed"
                break
            quality=inspect_png(data)
            if quality["status"]=="invalid":
                entry.update(stop_reason="invalid_frame",failed_frame=index,failed_quality=quality)
                break
            visual=None
            diff=None
            geometry_changed=dom_changed=None
            motion=compare_motion(previous,state) if track else []
            if previous is not None:
                visual,diff=visual_diff(previous_bytes,data)
                geometry_changed=(abs(state["scroll_y"]-previous["scroll_y"])>2 or
                                  abs(state["document_height"]-previous["document_height"])>2)
                dom_changed=(state["dom_count"]!=previous["dom_count"] or
                             state["dom_hash"]!=previous["dom_hash"])
                stable=stable+1 if not geometry_changed and not dom_changed else 0
            # Keep raw frame and map within a sequence byte budget. Metadata
            # stores bounded motion samples rather than duplicating every node.
            motion_count=len(motion)
            frame={"index":index,"scroll_y":state["scroll_y"],
                   "document_height":state["document_height"],"max_scroll":state["max_scroll"],
                   "viewport_height":state["viewport_height"],"dom_count":state["dom_count"],
                   "dom_hash":state["dom_hash"],"geometry_changed":geometry_changed,
                   "dom_changed":dom_changed,"visual_diff_percent":visual,
                   "visual_changed":visual>=threshold if visual is not None else None,
                   "motion_count":motion_count,"motion":motion[:40],
                   "motion_truncated":motion_count>40 or state["motion_sample_truncated"],
                   "dom_sample_truncated":state["dom_sample_truncated"],
                   "stable_count":stable,"at_bottom":state["scroll_y"]>=state["max_scroll"]-3,
                   "scroll_fallback_used":fallback,"quality":quality}
            needed=len(data)+(len(diff) if diff is not None else 0)
            if total_bytes+needed>MAX_SEQUENCE_BYTES:
                entry["stop_reason"]="byte_budget"
                break
            frame["screenshot"]=write_bytes(root,prefix/f"frame-{index:03d}.png",data)
            if diff is not None:
                frame["difference_map"]=write_bytes(root,prefix/f"diff-{index:03d}.png",diff)
            total_bytes+=needed
            entry["frames"].append(frame)
            entry["status"]="partial"
            entry["bytes"]=total_bytes
            entry["elapsed_ms"]=int((monotonic()-start)*1000)
            if stable>=stable_limit:
                entry["stop_reason"]="bottom_reached" if frame["at_bottom"] else "scroll_stalled_before_bottom"
                if frame["at_bottom"]:
                    entry["status"]="captured"
                checkpoint(entry)
                break
            checkpoint(entry)
            previous,previous_bytes=state,data
            if index+1>=options.get("max_frames",150):
                break
            page.mouse.move(viewport["width"]/2,viewport["height"]/2)
            page.mouse.wheel(0,step)
            pause(page,deadline,cancelled,settle)
            fallback=False
            if mobile and not frame["at_bottom"] and remaining_ms(deadline)>0:
                current_y=page.evaluate("document.scrollingElement.scrollTop")
                if abs(current_y-state["scroll_y"])<=2:
                    page.evaluate("(step)=>window.scrollBy(0,step)",step)
                    pause(page,deadline,cancelled,settle)
                    fallback=True
    except CaptureCancelled:
        raise
    except Exception as exc:
        entry["stop_reason"]="timeline_timeout" if type(exc).__name__=="TimeoutError" else "timeline_failed"
    finally:
        if context is not None:
            context.close()
        if entry["status"]=="not_attempted":
            entry["status"]="failed"
        entry["elapsed_ms"]=int((monotonic()-start)*1000)
        entry["frame_count"]=len(entry["frames"])
    return entry
