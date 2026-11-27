"""Opt-in ordered viewport evidence; independent fresh context per sequence."""
import hashlib
import json
from pathlib import Path
from time import monotonic, perf_counter
from .browser import context_for
from .cookie_consent import handle_cookie_consent
from .page_readiness import check_cancelled, remaining_ms, pause, wait_ready
from .pipeline import CaptureCancelled
from .screenshot_quality import inspect_png
from .scroll_engine import ScrollEngine
from .scroll_detection import snapshot_scroll
from .scroll_performance import DOM_CANDIDATES, PerformanceDiagnostics, release_dom_cache
from .scroll_pixel_diff import PIXEL_THRESHOLD, PixelDiffSequence, visual_diff
from .horizontal_capture import PROBE as HORIZONTAL_PROBE, eligible, build_panorama, build_storyboard

MAX_SEQUENCE_BYTES = 96 * 1024 * 1024
LIMITATIONS = [
    "Viewport pixel difference includes ordinary scrolling, carousels and animation.",
    "DOM signature is sampled; not a complete DOM diff.",
    "Motion uses sampled visible nodes and scroll-adjusted geometry; not causal animation inference.",
    "Bottom and geometry/DOM stability are observational, not proof of complete lazy loading.",
    "No arbitrary drag or scripted user actions; mobile may use scrollBy fallback.",
    "Autonomous animation and pixel change alone do not establish scroll progress.",
    "Transform-only completion is unverified without a measurable scroll extent.",
]

SNAPSHOT = r"""
(track) => {""" + DOM_CANDIDATES + r"""
    const doc=document.scrollingElement;
    const limit=nodes.length;
    window.__stTimelineIds ??= new WeakMap();
    window.__stTimelineCounter ??= 0;
    const tags=[],elements=[];
    for(let i=0;i<limit;i++){
        const el=nodes[i];
        tags.push(el.tagName);
        if(!track||elements.length>=500)continue;
        const r=rect(el);
        if(r.width<1||r.height<1||r.bottom<=0||r.top>=innerHeight||r.right<=0||r.left>=innerWidth)continue;
        const s=style(el);
        if(s.visibility==='hidden'||s.display==='none')continue;
        metrics.visible_elements_sampled++;
        if(!window.__stTimelineIds.has(el))window.__stTimelineIds.set(el,++window.__stTimelineCounter);
        const round=n=>Math.round(n*10)/10;
        elements.push({id:window.__stTimelineIds.get(el),tag:el.tagName,
          class:(el.getAttribute('class')||'').slice(0,160),
          x:round(r.x),y:round(r.y),width:round(r.width),height:round(r.height),
          transform:s.transform,opacity:s.opacity,position:s.position});
    }
    metrics.geometry_reads+=2;
    const height=doc.scrollHeight;
    return {scroll_y:Math.round(doc.scrollTop),document_height:height,
      viewport_height:innerHeight,max_scroll:Math.max(0,height-innerHeight),
      dom_count:domCount,tags,text:(document.body.innerText||'').slice(0,100000),
      visible_elements:elements,dom_sample_truncated:domCount>limit,
      motion_sample_truncated:track&&elements.length>=500,_performance:metrics};
}
"""


def snapshot(page, track, diagnostics=None):
    started=perf_counter()
    state=page.evaluate(SNAPSHOT,track)
    signature=json.dumps([state.pop("tags"),state.pop("text")],ensure_ascii=False)
    state["dom_hash"]=hashlib.sha256(signature.encode()).hexdigest()
    if diagnostics is None:
        state.pop("_performance",None)
    else:
        diagnostics.snapshot(state,"timeline_snapshot_ms",started)
    return state


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
    horizontal=eligible(url,viewport)
    step=profile.get("step_px",600 if mobile else 250)
    settle=profile.get("settle_ms",800 if mobile else 1500)
    track=profile.get("motion_tracking",not mobile)
    threshold=options.get("visual_threshold_percent",0.5)
    stable_limit=options.get("stable_steps",5)
    entry={"url":url,"viewport":viewport["name"],"status":"not_attempted",
           "step_px":step,"settle_ms":settle,"motion_tracking":track,
           "visual_threshold_percent":threshold,"pixel_threshold":PIXEL_THRESHOLD,
           "stable_steps":stable_limit,"frames":[],"stop_reason":"not_attempted"}
    context=page=None
    previous=None
    diagnostics=PerformanceDiagnostics()
    pixel_diff=PixelDiffSequence(diagnostics)
    stable=0
    total_bytes=0
    engine=None
    last_step=None
    popups=[]
    navigations=[]
    if horizontal:
        entry["horizontal_panorama"]={"status":"unavailable","reason":"no_verified_horizontal_strip"}
        entry["horizontal_storyboard"]={"status":"unavailable","reason":"insufficient_frames"}

    def horizontal_probe():
        started=perf_counter()
        try:
            observation=page.evaluate(HORIZONTAL_PROBE)
            diagnostics.snapshot(observation,"timeline_snapshot_ms",started)
            return observation["candidate"]
        except Exception:
            # Supplemental evidence cannot invalidate a regular timeline.
            return None

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
        engine=ScrollEngine(page,cancelled,mobile=mobile,diagnostics=diagnostics)
        entry["stop_reason"]="max_frames"
        for index in range(options.get("max_frames",150)):
            check_cancelled(cancelled)
            if remaining_ms(deadline)<=0:
                entry["stop_reason"]="time_budget"
                break
            if page.url!=url or navigations or popups:
                entry["stop_reason"]="navigation_changed"
                break
            state=snapshot(page,track,diagnostics)
            candidate=horizontal_probe() if horizontal and remaining_ms(deadline)>0 else None
            left=remaining_ms(deadline)
            if left<=0:
                entry["stop_reason"]="time_budget"
                break
            data=page.screenshot(full_page=False,animations="allow",scale="css",timeout=min(15000,left))
            check_cancelled(cancelled)
            if page.url!=url or navigations or popups:
                entry["stop_reason"]="navigation_changed"
                break
            if candidate is not None:
                # Geometry must agree on both sides of the actual screenshot.
                if remaining_ms(deadline)<=0 or horizontal_probe()!=candidate:
                    candidate=None
            phase=perf_counter()
            quality=inspect_png(data)
            diagnostics.add_time("other_processing_ms",phase)
            if quality["status"]=="invalid":
                entry.update(stop_reason="invalid_frame",failed_frame=index,failed_quality=quality)
                break
            phase=perf_counter()
            geometry_changed=dom_changed=None
            motion=compare_motion(previous,state) if track else []
            diagnostics.add_time("other_processing_ms",phase)
            visual,diff=pixel_diff.advance(data)
            phase=perf_counter()
            if previous is not None:
                geometry_changed=(abs(state["scroll_y"]-previous["scroll_y"])>2 or
                                  abs(state["document_height"]-previous["document_height"])>2)
                dom_changed=(state["dom_count"]!=previous["dom_count"] or
                             state["dom_hash"]!=previous["dom_hash"])
                stable=stable+1 if not geometry_changed and not dom_changed and not (last_step or {}).get("progress") else 0
            # Keep raw frame and map within a sequence byte budget. Metadata
            # stores bounded motion samples rather than duplicating every node.
            motion_count=len(motion)
            diagnostics.add_time("other_processing_ms",phase)
            # This is after the screenshot/diff: never reuse pre-frame geometry.
            scroll_state=snapshot_scroll(page,diagnostics)
            phase=perf_counter()
            measurable_end=engine.end(scroll_state)
            # A genuinely short static document is not a custom transform scene.
            static_end=(not engine.modes and scroll_state["root"]["max_y"]<=3
                        and scroll_state["root"]["max_x"]<=3 and not scroll_state["containers"]
                        and not scroll_state["truncated"])
            frame={"index":index,"scroll_y":state["scroll_y"],
                   "document_height":state["document_height"],"max_scroll":state["max_scroll"],
                   "viewport_height":state["viewport_height"],"dom_count":state["dom_count"],
                   "dom_hash":state["dom_hash"],"geometry_changed":geometry_changed,
                   "dom_changed":dom_changed,"visual_diff_percent":visual,
                   "visual_changed":visual>=threshold if visual is not None else None,
                   "motion_count":motion_count,"motion":motion[:40],
                   "motion_truncated":motion_count>40 or state["motion_sample_truncated"],
                   "dom_sample_truncated":state["dom_sample_truncated"],
                   "stable_count":stable,"at_bottom":measurable_end or static_end,
                   "scroll_fallback_used":bool((last_step or {}).get("fallback_used")),
                   "scroll_observation":last_step,"scroll_geometry":{"root":scroll_state["root"],
                       "containers":scroll_state["containers"],"sample_truncated":scroll_state["truncated"]},
                   "quality":quality}
            if candidate is not None:
                frame["horizontal_candidate"]=candidate
            needed=len(data)+(len(diff) if diff is not None else 0)
            if total_bytes+needed>MAX_SEQUENCE_BYTES:
                diagnostics.add_time("other_processing_ms",phase)
                entry["stop_reason"]="byte_budget"
                break
            frame["screenshot"]=write_bytes(root,prefix/f"frame-{index:03d}.png",data)
            if diff is not None:
                frame["difference_map"]=write_bytes(root,prefix/f"diff-{index:03d}.png",diff)
            total_bytes+=needed
            entry["frames"].append(frame)
            entry["status"]="partial"
            entry["scroll_intelligence"]=engine.summary()
            entry["bytes"]=total_bytes
            entry["elapsed_ms"]=int((monotonic()-start)*1000)
            diagnostics.add_time("other_processing_ms",phase)
            entry["performance"]=diagnostics.report()
            if stable>=stable_limit:
                entry["stop_reason"]=("bottom_reached" if frame["at_bottom"] else
                    "transform_end_unverified" if engine.transform_only and not engine.targets else
                    "scroll_stalled_before_bottom")
                if frame["at_bottom"]:
                    entry["status"]="captured"
                checkpoint(entry)
                break
            checkpoint(entry)
            previous=state
            if index+1>=options.get("max_frames",150):
                break
            last_step=engine.step(step,settle,deadline)
            if last_step is None:
                entry["stop_reason"]="time_budget"
                break
        if horizontal and entry["frames"] and entry["stop_reason"]!="navigation_changed":
            try:
                report,panorama=build_panorama(root,entry["frames"],deadline,cancelled,
                                               MAX_SEQUENCE_BYTES-total_bytes)
                if panorama is not None:
                    report["image"]=write_bytes(root,prefix/"horizontal-panorama.png",panorama)
                    total_bytes+=len(panorama)
                    entry["bytes"]=total_bytes
                entry["horizontal_panorama"]=report
            except CaptureCancelled:
                raise
            except Exception:
                entry["horizontal_panorama"]={"status":"unavailable","reason":"derivation_failed"}
            # Independent fallback: animation or overlap failure is not
            # grounds to discard the observed sequence.
            try:
                report,storyboard=build_storyboard(root,entry["frames"],deadline,cancelled,
                                                  MAX_SEQUENCE_BYTES-total_bytes)
                if storyboard is not None:
                    report["image"]=write_bytes(root,prefix/"horizontal-storyboard.png",storyboard)
                    total_bytes+=len(storyboard)
                    entry["bytes"]=total_bytes
                entry["horizontal_storyboard"]=report
            except CaptureCancelled:
                raise
            except Exception:
                entry["horizontal_storyboard"]={"status":"unavailable","reason":"derivation_failed"}
    except CaptureCancelled:
        raise
    except Exception as exc:
        entry["stop_reason"]="timeline_timeout" if type(exc).__name__=="TimeoutError" else "timeline_failed"
    finally:
        pixel_diff.close()
        if context is not None:
            # Context close releases all document state even on cancellation.
            release_dom_cache(page)
            context.close()
        if entry["status"]=="not_attempted":
            entry["status"]="failed"
        entry["elapsed_ms"]=int((monotonic()-start)*1000)
        entry["frame_count"]=len(entry["frames"])
        entry["performance"]=diagnostics.report()
    return entry
