"""Explicit, isolated visual state probes; not an arbitrary browser script runner."""
import hashlib
from pathlib import Path
from urllib.parse import urlsplit

from .browser import context_for
from .pipeline import CaptureCancelled

LIMITATIONS = [
    "One declared action per fresh browser context; no typing, submission, authentication or arbitrary scripts.",
    "Network is disabled after initial load; states requiring new resources may be incomplete.",
    "An image is an observation, not proof of semantic success unless an explicit expectation is checked.",
    "Trusted authorized public references only; offline mode and DOM checks are not a hostile-site sandbox.",
]

TARGET_JS = r"""
(el) => {
  const rect=el.getBoundingClientRect(), style=getComputedStyle(el);
  const interactiveAncestor=el.closest('a,form,input,textarea,select,label,[contenteditable]:not([contenteditable="false"]),[role="link"]');
  const unsafe=!!interactiveAncestor || !!el.form || el.matches(':disabled,[aria-disabled="true"],[download],iframe,object,embed');
  const summary=el.localName==='summary' && el.parentElement?.localName==='details';
  const button=el.localName==='button' && (!el.hasAttribute('type') || el.type==='button');
  const toggle=el.getAttribute('role')==='button' &&
    (el.hasAttribute('aria-expanded') || el.hasAttribute('aria-controls') || el.hasAttribute('aria-haspopup'));
  const label=(el.getAttribute('aria-label') || el.innerText || '').slice(0,200);
  const destructive=/\b(delete|remove|purchase|buy|pay|checkout|submit|sign\s*(in|up|out)|log\s*(in|out)|logout|subscribe|unsubscribe|confirm|send|transfer|order)\b/i.test(label);
  return {
    safe_control:!unsafe && !destructive && (summary || button || toggle),
    visible:rect.width>0 && rect.height>0 && style.visibility==='visible' && style.display!=='none',
    tag:el.localName,
    expanded:el.getAttribute('aria-expanded'),
    details_open:summary?el.parentElement.open:null,
    focused:document.activeElement===el,
    hovered:el.matches(':hover'),
    rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},
    style:{color:style.color,background:style.backgroundColor,opacity:style.opacity,
           transform:style.transform,outline:style.outline,display:style.display}
  };
}
"""

class SkippedState(ValueError):
    """An action is unsupported or rejected before it is attempted."""


def planned_states(config, routes, views):
    by_path={urlsplit(url).path or "/":url for url in routes}
    result=[]
    for scenario in config.get("interactions", {}).get("scenarios", []):
        for view in views:
            if view["name"] not in scenario.get("viewports", [v["name"] for v in views]):
                continue
            result.append({
                "id":scenario["id"], "url":by_path[scenario["route"]],
                "viewport":view["name"], "width":view["width"], "height":view["height"],
                "action":scenario["action"], "selector":scenario.get("selector"),
                "expect_visible":scenario.get("expect_visible"),
                "scroll_y":scenario.get("scroll_y"), "wait_ms":scenario.get("wait_ms",350),
                "status":"not_attempted",
            })
    return result


def unique_target(page, selector):
    locator=page.locator("css="+selector)
    if locator.count()!=1:
        raise SkippedState("Selector must match exactly one element")
    handle=locator.element_handle(timeout=1500)
    if handle is None:
        raise SkippedState("Target missing")
    return handle


def observe(page, state):
    action=state["action"]
    before={"scroll_y":page.evaluate("() => scrollY")}
    if action=="scroll":
        page.evaluate("(y) => window.scrollTo({top:y,behavior:'instant'})",state["scroll_y"])
        page.wait_for_timeout(state["wait_ms"])
        after={"scroll_y":page.evaluate("() => scrollY")}
        if after["scroll_y"]==before["scroll_y"]:
            raise ValueError("Requested scroll did not change position")
    else:
        if action=="hover" and not page.evaluate("() => matchMedia('(hover: hover)').matches"):
            raise SkippedState("Hover unavailable on this viewport")
        handle=unique_target(page,state["selector"])
        before["target"]=handle.evaluate(TARGET_JS)
        if not before["target"]["visible"]:
            raise SkippedState("Target not visible")
        if action in ("click","focus") and not before["target"]["safe_control"]:
            raise SkippedState("Target is not a permitted UI control")
        if action=="hover":
            handle.hover(timeout=2000)
        elif action=="focus":
            handle.focus()
        elif action=="click":
            if state["width"]<600:
                handle.tap(timeout=2000)
            else:
                handle.click(timeout=2000)
        else:
            raise ValueError("Unsupported action")
        page.wait_for_timeout(state["wait_ms"])
        after={"scroll_y":page.evaluate("() => scrollY")}
        # A menu may replace its trigger. Do not treat detachment as a successful assertion.
        try:
            after["target"]=handle.evaluate("(el) => el.isConnected ? ("+TARGET_JS+")(el) : null")
        except Exception:
            after["target"]=None
        if action=="focus" and not (after["target"] or {}).get("focused"):
            raise ValueError("Focus not observed")
        if action=="hover" and not (after["target"] or {}).get("hovered"):
            raise ValueError("Hover not observed")
    expectation=state.get("expect_visible")
    verified=None
    if expectation:
        target=page.locator("css="+expectation)
        verified=target.count()==1 and target.is_visible()
        if not verified:
            raise ValueError("Expected visible element not observed")
    return before,after,verified


def capture_state(browser, viewport, expected, root: Path, state, cancelled=lambda:False):
    if cancelled():
        raise CaptureCancelled("Capture cancelled before interaction")
    result=dict(state)
    gate={"closed":False,"blocked":0}
    context=None
    target=None
    try:
        context=context_for(browser,viewport,expected,network_gate=gate)
        page=context.new_page()
        popups=[]
        def close_popup(popup):
            popups.append(True)
            popup.close()
        context.on("page",close_popup)
        response=page.goto(state["url"],wait_until="domcontentloaded",timeout=10000)
        if response is None or response.status>=400:
            raise ValueError("Initial state load failed")
        page.wait_for_timeout(700)
        if page.url!=state["url"] or popups:
            raise ValueError("Initial state navigated away or opened a popup")
        # Fresh context has no imported cookies/auth. From here no requests may
        # be initiated through the route handler; offline mode adds a second barrier.
        gate["closed"]=True
        context.set_offline(True)
        navigated=[]
        page.on("framenavigated",lambda frame:navigated.append(True) if frame==page.main_frame else None)
        page.evaluate("""() => {
            document.addEventListener('submit', e=>{e.preventDefault();e.stopImmediatePropagation()}, true);
            document.addEventListener('click', e=>{
                if(e.target instanceof Element && e.target.closest('a,form,[download]')) {
                    e.preventDefault();e.stopImmediatePropagation();
                }
            }, true);
        }""")
        if cancelled():
            raise CaptureCancelled("Capture cancelled before action")
        before,after,verified=observe(page,state)
        if cancelled():
            raise CaptureCancelled("Capture cancelled after action")
        if page.url!=state["url"] or navigated or popups:
            raise ValueError("Interaction attempted navigation or popup")
        relative=Path("interactions")/state["viewport"]/(state["id"]+".png")
        target=root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        # Viewport screenshot preserves scroll and sticky UI; animations sampled as-is.
        page.screenshot(path=str(target),full_page=False,animations="allow",timeout=5000)
        if cancelled():
            raise CaptureCancelled("Capture cancelled after state screenshot")
        if page.url!=state["url"] or navigated or popups:
            raise ValueError("Page changed during state screenshot")
        result.update(status="captured",path=relative.as_posix(),
                      sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      before=before,after=after,expectation_verified=verified)
    except CaptureCancelled:
        raise
    except SkippedState as exc:
        result.update(status="skipped",reason=str(exc))
    except Exception:
        # Do not put raw Playwright messages (potentially URL secrets/page content) into evidence.
        result.update(status="failed",reason="State load, action, assertion or screenshot failed")
    finally:
        if context is not None:
            context.close()
    result["blocked_requests"]=gate["blocked"]
    if result["status"]!="captured" and target is not None:
        target.unlink(missing_ok=True)
    return result
