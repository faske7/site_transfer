"""Bounded observations of document, nested scroll and rendered transforms.

No framework-specific selectors or injected scrolling styles. Observations
are not proof that an animation is causally driven by scroll.
"""

from time import perf_counter

from .scroll_performance import DOM_CANDIDATES

SAMPLE = r"""
() => {""" + DOM_CANDIDATES + r"""
    const doc=document.scrollingElement || document.documentElement;
    const round=n=>Math.round(n*10)/10;
    const position=(el,s,maxX,maxY)=>{
        metrics.geometry_reads+=2;
        return {x:round(el.scrollLeft),y:round(el.scrollTop),
            max_x:Math.max(0,maxX??extent(el,'x')),
            max_y:Math.max(0,maxY??extent(el,'y')),
            rtl:(s||style(el)).direction==='rtl'};
    };
    // Store identity rather than unstable DOM indexes across hydration.
    window.__stScrollIds ??= new WeakMap();
    window.__stScrollCounter ??= 0;
    const id=el=>{
        if(!window.__stScrollIds.has(el))window.__stScrollIds.set(el,++window.__stScrollCounter);
        return window.__stScrollIds.get(el);
    };
    const containers=[],transforms=[];
    let containerTruncated=false,transformTruncated=false;
    for(let i=0;i<nodes.length;i++){
        const el=nodes[i];
        if(el===doc||el===document.body||el===document.documentElement)continue;
        const r=rect(el);
        const left=Math.max(0,r.left),right=Math.min(innerWidth,r.right);
        const top=Math.max(0,r.top),bottom=Math.min(innerHeight,r.bottom);
        if(right-left<2||bottom-top<2)continue;
        const s=style(el);
        if(s.display==='none'||s.visibility==='hidden')continue;
        metrics.visible_elements_sampled++;
        let maxX,maxY;
        const sx=/^(auto|scroll|overlay)$/.test(s.overflowX)&&(maxX=extent(el,'x'))>2;
        const sy=/^(auto|scroll|overlay)$/.test(s.overflowY)&&(maxY=extent(el,'y'))>2;
        if(sx||sy){
            if(containers.length<32)containers.push({...position(el,s,maxX,maxY),id:id(el),
                tag:el.tagName.toLowerCase(),scrollable_x:sx,scrollable_y:sy,
                point:[round((left+right)/2),round((top+bottom)/2)],
                area:round((right-left)*(bottom-top))});
            else containerTruncated=true;
        }
        if(transforms.length<500){
            // Include 'none' so the first transition from no transform is observed.
            transforms.push({id:id(el),transform:s.transform,
                translate:s.translate||'none',rotate:s.rotate||'none',scale:s.scale||'none',
                position:s.position,top:s.top,left:s.left});
        }else transformTruncated=true;
    }
    containers.sort((a,b)=>b.area-a.area||a.id-b.id);
    return {root:position(doc),viewport:[innerWidth,innerHeight],
      containers,transforms,truncated:domCount>5000||containerTruncated||transformTruncated,_performance:metrics};
}
"""


def snapshot_scroll(page, diagnostics=None):
    started=perf_counter()
    state=page.evaluate(SAMPLE)
    if diagnostics is None:
        state.pop("_performance",None)
    else:
        diagnostics.snapshot(state,"scroll_snapshot_ms",started)
    return state


def coordinate_changes(before, after):
    result=[]
    pairs=[("document",before["root"],after["root"])]
    old={item["id"]:item for item in before["containers"]}
    pairs.extend((item["id"],old[item["id"]],item)
                 for item in after["containers"] if item["id"] in old)
    for identity,a,b in pairs:
        dx=round(b["x"]-a["x"],2)
        dy=round(b["y"]-a["y"],2)
        if abs(dx)>2 or abs(dy)>2:
            result.append({"target":identity,"dx":dx,"dy":dy})
    return result


def transform_changes(before,after):
    old={item["id"]:item for item in before["transforms"]}
    changed=set()
    for item in after["transforms"]:
        a=old.get(item["id"])
        if a is None:
            continue
        fields=["transform","translate","rotate","scale"]
        if item["position"] in ("absolute","fixed","sticky","relative"):
            fields.extend(["top","left"])
        if any(a[k]!=item[k] for k in fields):
            changed.add(item["id"])
    return changed


def classify(before,after,idle=None):
    coordinates=coordinate_changes(before,after)
    transforms=transform_changes(before,after)
    autonomous=transform_changes(idle,before) if idle is not None else set()
    responsive=transforms-autonomous
    modes=set()
    for change in coordinates:
        if change["target"]!="document":
            modes.add("nested")
        if abs(change["dx"])>2:
            modes.add("horizontal")
        if abs(change["dy"])>2:
            modes.add("vertical")
    if responsive:
        modes.add("transform")
    return {"modes":sorted(modes),"progress":bool(coordinates or responsive),
            "coordinate_changes":coordinates,
            "transform_count":len(responsive),
            "transform_ids":sorted(responsive)[:40],
            "idle_motion_count":len(autonomous),
            "sample_truncated":before["truncated"] or after["truncated"]}


def at_end(state, targets):
    """Only coordinates with a measurable extent can establish completion."""
    root=state["root"]
    axes=targets.get("document",set())
    if not axes and not targets:
        return False
    containers={c["id"]:c for c in state["containers"]}
    for target,used_axes in targets.items():
        item=root if target=="document" else containers.get(target)
        if item is None:
            return False
        for axis in used_axes:
            if abs(item[axis])<item["max_"+axis]-3:
                return False
    # Do not call a nested-only sequence complete while the document itself
    # still has an untraversed vertical extent.
    if root["max_y"]>3 and root["y"]<root["max_y"]-3:
        return False
    return True
