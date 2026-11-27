"""Bounded document candidates and sequence-scoped performance counters."""
from time import perf_counter
import sys

try:
    import resource
except ImportError:  # optional diagnostic on non-POSIX hosts
    resource = None


DOM_COUNTERS = (
    "dom_cache_hits", "dom_cache_misses", "dom_cache_invalidations",
    "dom_full_scans", "geometry_reads", "computed_style_reads",
    "visible_elements_sampled",
)
TIME_COUNTERS = (
    "scroll_snapshot_ms", "timeline_snapshot_ms", "pixel_diff_ms",
    "png_decode_ms", "other_processing_ms",
)

# Cache only the bounded candidate list and exact total count. Geometry and
# styles are read within the current synchronous evaluate, never across calls.
DOM_CANDIDATES = r"""
    const metrics={dom_cache_hits:0,dom_cache_misses:0,dom_cache_invalidations:0,
        dom_full_scans:0,geometry_reads:0,computed_style_reads:0,visible_elements_sampled:0};
    const owner=document;
    const key='__stScrollCandidateCacheV1';
    let cache=owner[key];
    if(!cache){
        cache={nodes:null,count:0,body:null,invalidations:0};
        cache.invalidate=()=>{
            if(cache.nodes!==null)cache.invalidations++;
            cache.nodes=null;cache.body=null;cache.count=0;
        };
        cache.observer=new MutationObserver(cache.invalidate);
        cache.observer.observe(owner,{childList:true,subtree:true});
        cache.release=()=>{
            cache.observer.disconnect();cache.invalidate();
            window.removeEventListener('pagehide',cache.release);
            if(owner[key]===cache)delete owner[key];
        };
        owner[key]=cache;
        window.addEventListener('pagehide',cache.release,{once:true});
    }
    // A synchronous mutation can precede the observer callback in this task.
    if(cache.observer.takeRecords().length||cache.body!==owner.body)cache.invalidate();
    metrics.dom_cache_invalidations=cache.invalidations;cache.invalidations=0;
    if(cache.nodes===null){
        const body=owner.body;
        const collection=body?.getElementsByTagName('*')||[];
        cache.count=collection.length;cache.body=body;
        cache.nodes=[];
        for(let i=0;i<Math.min(cache.count,5000);i++)cache.nodes.push(collection[i]);
        metrics.dom_cache_misses++;metrics.dom_full_scans++;
    }else metrics.dom_cache_hits++;
    const nodes=cache.nodes,domCount=cache.count;
    const rect=el=>{metrics.geometry_reads++;return el.getBoundingClientRect()};
    const style=el=>{metrics.computed_style_reads++;return getComputedStyle(el)};
    const extent=(el,axis)=>{
        metrics.geometry_reads+=2;
        return axis==='x'?el.scrollWidth-el.clientWidth:el.scrollHeight-el.clientHeight;
    };
"""


def release_dom_cache(page):
    """Best effort: context destruction also releases document-owned resources."""
    if page is not None:
        try:
            page.evaluate("() => document.__stScrollCandidateCacheV1?.release()")
        except Exception:
            pass  # navigation/closed page must not mask cancellation or failure


class PerformanceDiagnostics:
    def __init__(self):
        self.values = dict.fromkeys(DOM_COUNTERS + TIME_COUNTERS, 0)

    def add_time(self, key, started):
        self.values[key] += (perf_counter() - started) * 1000

    def snapshot(self, state, key, started):
        counters = state.pop("_performance", {})
        for name in DOM_COUNTERS:
            self.values[name] += counters.get(name, 0)
        self.add_time(key, started)

    def report(self):
        values = dict(self.values)
        values["total_processing_ms"] = sum(values[name] for name in TIME_COUNTERS
                                            if name != "png_decode_ms")
        for name in TIME_COUNTERS + ("total_processing_ms",):
            values[name] = round(values[name], 3)
        # Process lifetime high-water mark, not a per-sequence allocation peak
        # or browser RSS. It is monotonic and includes native Pillow buffers.
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None
        values["peak_memory"] = None if peak is None else peak * (1 if sys.platform == "darwin" else 1024)
        values["peak_memory_scope"] = "python_process_high_water_bytes"
        return values
