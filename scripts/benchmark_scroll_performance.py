"""Opt-in, same-browser PR-16/PR-17 component benchmark (no timing assertions).

Run from PR-17 with --baseline pointing to a detached PR-16 worktree.
"""
import argparse
import ast
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import platform
from statistics import median
from time import perf_counter, process_time

from PIL import Image
from playwright.sync_api import sync_playwright
from site_transfer.scroll_detection import SAMPLE
from site_transfer.scroll_timeline import SNAPSHOT
from site_transfer.scroll_pixel_diff import PixelDiffSequence
from site_transfer.scroll_performance import release_dom_cache


def baseline_code(root, name, symbol):
    tree = ast.parse((root / "src" / "site_transfer" / name).read_text())
    return next(n for n in tree.body if (
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == symbol for t in n.targets)
    ) or (isinstance(n, ast.FunctionDef) and n.name == symbol))


def summary(values):
    return {"median": round(median(values), 3),
            "p95": round(sorted(values)[math.ceil(.95 * len(values)) - 1], 3),
            "samples": [round(v, 3) for v in values]}


def timed(fn):
    w,c=perf_counter(),process_time()
    result=fn()
    return result,(perf_counter()-w)*1000,(process_time()-c)*1000


def make_fixture():
    return """<!doctype html><style>body{margin:0}.row{height:35px;background:#eff3ff}
    .row:nth-child(2n){background:#a7b9cf}.fixed{position:fixed;top:0;right:0;background:red}
    .panel{position:sticky;top:0;width:160px;height:80px;overflow:auto;direction:rtl}
    .panel div{width:400px;height:250px}</style><div class="fixed">Fixed</div>
    <div class="panel"><div>Nested</div></div>""" + "".join(
        '<div class="row">Row %d</div>' % i for i in range(4997))


def decoded_hash(data):
    with Image.open(BytesIO(data)) as im:
        return hashlib.sha256(im.tobytes()).hexdigest()


def capture_inputs(browser, viewport, html):
    with browser.new_context(viewport=viewport) as context:
        page=context.new_page()
        page.set_content(html)
        frames=[]
        for i in range(15):
            page.evaluate("(y)=>scrollTo(0,y)",i*250)
            frames.append(page.screenshot(animations="allow",scale="css"))
        return frames


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--baseline",type=Path,required=True)
    parser.add_argument("--runs",type=int,default=7)
    parser.add_argument("--executable-path",default=None)
    args=parser.parse_args()
    if args.runs<5:
        parser.error("at least five measured runs")
    legacy_sample=ast.literal_eval(baseline_code(args.baseline,"scroll_detection.py","SAMPLE").value)
    legacy_timeline=ast.literal_eval(baseline_code(args.baseline,"scroll_timeline.py","SNAPSHOT").value)
    from PIL import ImageChops
    ns={"Image":Image,"ImageChops":ImageChops,"BytesIO":BytesIO,"PIXEL_THRESHOLD":12}
    func=baseline_code(args.baseline,"scroll_timeline.py","visual_diff")
    exec(compile(ast.Module(body=[func],type_ignores=[]),"<baseline>","exec"),ns)
    old_diff=ns["visual_diff"]
    report={"platform":platform.platform(),"python":platform.python_version(),
            "pillow":Image.__version__,"fixture_nodes":5000,"warmup_runs":1,
            "measured_runs":args.runs,"scope":"component benchmark; excludes page waits, screenshots and production capture"}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=args.executable_path)
        report["browser"]=browser.version
        html=make_fixture()
        for viewport in [{"width":800,"height":600},{"width":390,"height":844}]:
            frames=capture_inputs(browser,viewport,html)
            pairs=list(zip(frames,frames[1:]))
            expected=[(v,decoded_hash(d)) for v,d in (old_diff(a,b) for a,b in pairs)]
            results={}
            def dom_run(new):
                with browser.new_context(viewport=viewport) as ctx:
                    page=ctx.new_page()
                    page.set_content(html)
                    counters={}
                    states=[]
                    def run():
                        for i in range(10):
                            page.evaluate("(y)=>scrollTo(0,y)",i*250)
                            for script,args_ in [(SAMPLE if new else legacy_sample,()),
                                                 (SNAPSHOT if new else legacy_timeline,(True,))]:
                                state=page.evaluate(script,*args_)
                                for k,v in state.pop("_performance",{}).items():
                                    counters[k]=counters.get(k,0)+v
                                states.append(state)
                    _,wall,cpu=timed(run)
                    release_dom_cache(page)
                    return states,counters,wall,cpu
            old_states=dom_run(False)[0]
            new_states=dom_run(True)[0]
            assert old_states==new_states,"snapshot semantics changed"
            def diff_run(new):
                if not new:
                    return [old_diff(a,b) for a,b in pairs]
                with PixelDiffSequence() as seq:
                    seq.advance(frames[0])
                    return [seq.advance(f) for f in frames[1:]]
            assert [(v,decoded_hash(d)) for v,d in diff_run(True)]==expected
            for new in [False,True]:
                dom_run(new)
                diff_run(new)
            samples={new:{k:[] for k in ("dom_wall_ms","dom_python_cpu_ms","pixel_wall_ms","pixel_python_cpu_ms")} for new in (False,True)}
            for i in range(args.runs):
                for new in ([False,True] if i%2==0 else [True,False]):
                    _,counts,w,c=dom_run(new)
                    sample=samples[new]
                    sample["dom_wall_ms"].append(w)
                    sample["dom_python_cpu_ms"].append(c)
                    _,w,c=timed(lambda:diff_run(new))
                    sample["pixel_wall_ms"].append(w)
                    sample["pixel_python_cpu_ms"].append(c)
                    sample["dom_counters"]=counts if new else {"dom_candidate_requests":20}
            for new,sample in samples.items():
                results["after" if new else "before"]={k:summary(v) if isinstance(v,list) else v for k,v in sample.items()}
            report[str(viewport)]={"results":results,"frame_sha256":[hashlib.sha256(f).hexdigest() for f in frames],
                                   "equivalent_pairs":len(pairs),"dom_states_equal":True}
        browser.close()
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
