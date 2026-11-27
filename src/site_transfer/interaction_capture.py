"""Explicit, isolated visual state probes; not an arbitrary browser script runner."""
import hashlib
from time import monotonic
from pathlib import Path
from urllib.parse import urlsplit

from .browser import context_for, origin
from .pipeline import CaptureCancelled
from .screenshot_quality import inspect_png
from .page_readiness import wait_ready, check_cancelled
from .cookie_consent import handle_cookie_consent, consent_quality
from .scroll_engine import ScrollEngine
from .scroll_performance import PerformanceDiagnostics, release_dom_cache

LIMITATIONS = [
    "One declared action per fresh browser context (scroll may use bounded wheel steps); no typing, submission, authentication or arbitrary scripts.",
    "After preflight, scroll retains guarded public GET/HEAD resources; click, hover and focus are offline.",
    "An image is an observation, not proof of semantic success unless an explicit expectation is checked.",
    "Trusted authorized public references only; request guards and DOM checks are not a hostile-site sandbox. GET may have side effects.",
    "Recognized top-level client application error screens are rejected; other rendering failures may remain undetected.",
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


class StateFailure(ValueError):
    """Stable, sanitized state failure with optional numeric observations."""
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code=code
        self.details=details


def reject_application_crash(page):
    """Reject a visible, top-level Next.js error screen, not arbitrary console noise."""
    crashed=page.evaluate(r"""() => {
        const body=document.body;
        if(!body)return false;
        const text=(body.innerText||'').replace(/\s+/g,' ').trim();
        return text.length<=1200 && /Application error:\s*a client-side exception has occurred/i.test(text);
    }""")
    if crashed:
        raise StateFailure("application_crash","Client-side rendering failure")


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


def observe(page, state, cancelled=lambda:False):
    action=state["action"]
    before={"scroll_y":page.evaluate("() => scrollY")}
    if action=="scroll":
        diagnostics=PerformanceDiagnostics()
        engine=ScrollEngine(page,cancelled,mobile=state["width"]<600,diagnostics=diagnostics)
        report=engine.scroll_to(state["scroll_y"],state["wait_ms"],monotonic()+12)
        report["performance"]=diagnostics.report()
        before=report.pop("before")
        after=report.pop("after")
        after["scroll_observation"]=report
        try:
            reject_application_crash(page)
        except StateFailure as exc:
            exc.details.update(before=before,after=after)
            raise
        if not report["progress"]:
            raise StateFailure("scroll_unchanged","Requested scroll did not produce observed movement",
                               before=before,after=after)
        if report["target_reached"] is False:
            raise StateFailure("scroll_target_unreached","Requested document scroll target not reached",
                               before=before,after=after)
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
            raise StateFailure("focus_not_observed","Focus not observed")
        if action=="hover" and not (after["target"] or {}).get("hovered"):
            raise StateFailure("hover_not_observed","Hover not observed")
    expectation=state.get("expect_visible")
    verified=None
    if expectation:
        target=page.locator("css="+expectation)
        verified=target.count()==1 and target.is_visible()
        if not verified:
            raise StateFailure("expectation_not_met","Expected visible element not observed")
    return before,after,verified


def capture_state(browser, viewport, expected, root: Path, state, cancelled=lambda:False, *, consent_config=None):
    if cancelled():
        raise CaptureCancelled("Capture cancelled before interaction")
    result=dict(state)
    gate={"closed":False,"blocked":0}
    context=page=None
    target=None
    stage="navigation"
    start=monotonic()
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
            raise StateFailure("initial_load_failed","Initial state load failed")
        if page.url!=state["url"] or origin(page.url)!=expected or popups:
            raise StateFailure("navigation_changed","Initial state navigated away or opened a popup")
        stage="cookie_consent"
        consent=handle_cookie_consent(page,expected,consent_config,cancelled)
        result["cookie_consent"]=consent
        if consent["code"]=="navigation_changed" or popups or page.url!=state["url"]:
            raise StateFailure("navigation_changed","Cookie consent navigation rejected")
        stage="readiness"
        # Allow bounded normal loading before the offline gate; no action yet.
        result["readiness"]=wait_ready(page,monotonic()+5.0,cancelled,
                                       min_scroll=1 if state["action"]=="scroll" else 0)
        if page.url!=state["url"] or popups:
            raise StateFailure("navigation_changed","Initial state navigated away or opened a popup")
        check_cancelled(cancelled)
        stage="network_gate"
        # Scroll is wheel-only and may trigger lazy-loaded code/assets.
        # Keep the existing guarded public GET/HEAD transport in that case.
        # Explicit UI controls still use both offline barriers.
        if state["action"]=="scroll":
            gate["scroll_read_only"]=True
            result["network_mode"]="guarded_scroll"
        else:
            gate["closed"]=True
            context.set_offline(True)
            result["network_mode"]="offline"
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
        stage="action"
        reject_application_crash(page)
        before,after,verified=observe(page,state,cancelled)
        reject_application_crash(page)
        result.update(before=before,after=after,expectation_verified=verified)
        if cancelled():
            raise CaptureCancelled("Capture cancelled after action")
        if page.url!=state["url"] or navigated or popups or gate.get("navigation_attempted"):
            raise StateFailure("navigation_changed","Interaction attempted navigation or popup")
        relative=Path("interactions")/state["viewport"]/(state["id"]+".png")
        target=root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        # Viewport screenshot preserves scroll and sticky UI; animations sampled as-is.
        stage="screenshot"
        data=page.screenshot(full_page=False,animations="allow",timeout=8000)
        stage="validation"
        quality=inspect_png(data)
        result["quality"]=quality
        if quality["status"]=="invalid":
            raise StateFailure(quality["code"],"Invalid interaction PNG")
        if cancelled():
            raise CaptureCancelled("Capture cancelled after state screenshot")
        if page.url!=state["url"] or navigated or popups or gate.get("navigation_attempted"):
            raise StateFailure("navigation_changed","Page changed during state screenshot")
        reject_application_crash(page)
        warnings=[]
        if result["readiness"]["status"]!="settled":
            warnings.append("readiness_unsettled")
        if gate["blocked"]:
            warnings.append("network_requests_blocked")
        if state["action"]=="scroll" and after["scroll_observation"]["target_reached"] is None:
            warnings.append("scroll_target_not_measurable")
        if quality["status"]=="warning":
            warnings.append(quality["code"])
        if warnings:
            result["quality"]=dict(quality,status="warning",warnings=warnings)
        result["quality"]=consent_quality(result["quality"],consent)
        stage="publication"
        target.write_bytes(data)
        result.update(status="captured",path=relative.as_posix(),
                      sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      before=before,after=after,expectation_verified=verified)
    except CaptureCancelled:
        if target is not None:
            target.unlink(missing_ok=True)
        raise
    except SkippedState as exc:
        result.update(status="skipped",reason=str(exc),failure_stage=stage,code="unsafe_or_missing_target")
    except StateFailure as exc:
        result.update(status="failed",reason=str(exc),failure_stage=stage,code=exc.code,**exc.details)
    except Exception as exc:
        # Do not put raw Playwright messages (potentially URL secrets/page content) into evidence.
        code=stage+"_timeout" if type(exc).__name__=="TimeoutError" else stage+"_failed"
        result.update(status="failed",reason="Interaction "+code,failure_stage=stage,code=code)
    finally:
        if context is not None:
            if state["action"]=="scroll":
                release_dom_cache(page)
            context.close()
    result["blocked_requests"]=gate["blocked"]
    result["elapsed_ms"]=int((monotonic()-start)*1000)
    if result["status"]!="captured" and target is not None:
        target.unlink(missing_ok=True)
    return result
