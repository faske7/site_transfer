"""Opt-in, bounded cookie-banner interaction before reference capture.

No injected consent cookies, CSS hiding, arbitrary scripts, form submission,
cross-origin frame actions, or changes to the public browser network policy.
"""
import re
import unicodedata
from time import monotonic

from .browser import origin
from .page_readiness import check_cancelled, pause, remaining_ms
from .pipeline import CaptureCancelled

ROOTS = (
    "#onetrust-banner-sdk", "#CybotCookiebotDialog", "#uc-center-container",
    "#uc-banner", "#cmpbox", ".cky-consent-container", "#cookie-law-info-bar",
    "#cookie-banner", "#cookie-consent", ".cookie-banner", ".cookie-consent",
    "#cookieBanner", "#cookieConsent", "#cookies", ".cookies-banner",
    "[data-testid=\"cookie-banner\"]",
)
MAX_FRAMES = 5
MAX_ROOTS = 12
MAX_CONTROLS = 40
# Exact normalized strings only. Generic OK/Continue/Close/Confirm are excluded.
ACCEPT = {
    "accept all", "accept all cookies", "allow all", "allow all cookies",
    "agree to all cookies", "accept cookies",
    "přijmout vše", "přijmout všechny", "přijmout všechny cookies",
    "povolit vše", "povolit všechny", "povolit všechny cookies",
    "souhlasím se všemi cookies", "souhlasím se všemi", "souhlasím", "přijmout cookies",
    "alle akzeptieren", "alle cookies akzeptieren", "alles akzeptieren",
    "tout accepter", "accepter tous les cookies",
    "принять все", "принять все cookies", "принять все файлы cookie",
}
REJECT = {
    "reject all", "reject all cookies", "decline all", "deny all",
    "reject optional cookies", "reject non-essential cookies",
    "odmítnout vše", "odmítnout všechny", "odmítnout všechny cookies",
    "odmítnout volitelné", "alle ablehnen", "alles ablehnen",
    "tout refuser", "refuser tous les cookies", "отклонить все",
}
NECESSARY = {
    "necessary only", "only necessary cookies", "essential only",
    "use necessary cookies only", "accept necessary cookies only",
    "only essential cookies", "accept only necessary cookies",
    "pouze nezbytné", "pouze nezbytné cookies", "jen nezbytné",
    "pouze nutné", "pouze nutné cookies", "povolit pouze nezbytné",
    "přijmout pouze nezbytné", "jen nezbytné cookies",
    "nur notwendige cookies", "nur notwendige", "nur erforderliche",
    "cookies nécessaires uniquement", "только необходимые",
}
PROVIDER_IDS = {
    "accept_all": {"onetrust-accept-btn-handler", "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"},
    "reject_optional": {"onetrust-reject-all-handler", "CybotCookiebotDialogBodyButtonDecline"},
    "necessary_only": {"CybotCookiebotDialogBodyButtonDecline"},
}
CONTROL_JS = r"""
el => {
  let n=el;
  while(n){
    if(n.matches?.('a,form,label,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="link"],[download],iframe,object,embed')) return null;
    n=n.parentElement || n.getRootNode()?.host || null;
  }
  const button=el.localName==='button' || (el.localName==='input'&&el.type==='button') || el.getAttribute('role')==='button';
  if(!button || el.form || el.matches(':disabled,[aria-disabled="true"]')) return null;
  const label=(el.getAttribute('aria-label')||el.innerText||el.value||'').trim().slice(0,160);
  if(/\b(delete|remove|purchase|buy|pay|checkout|submit|sign\s*(in|up|out)|logout|subscribe|unsubscribe|send|transfer|order)\b/i.test(label)) return null;
  return {id:el.id,label};
}
"""
ROOT_JS = r"""
el => {
  const marker=[el.id,el.getAttribute('class'),el.getAttribute('data-testid'),
    el.getAttribute('aria-label'),el.innerText].filter(Boolean).join(' ').slice(0,3000);
  return /cookie|cookies|consent|soubory\s+cookie|soubory\s+cookies|onetrust|cookiebot|usercentrics|cmpbox|cky-consent/i.test(marker);
}
"""


def _normalize(label):
    return " ".join(unicodedata.normalize("NFKC",label).casefold().split()).strip(" .!?")


# Structural fallback for custom banners without cookie-specific IDs/classes.
# Require cookie subject matter AND opposing exact consent choices inside a
# visible fixed/sticky overlay or dialog. Never search for loose "OK" buttons.
CUSTOM_ROOT_JS = r"""
el => {
  if(!el.matches('div,section,aside,dialog,[role="dialog"],[role="alertdialog"]')) return false;
  const s=getComputedStyle(el),r=el.getBoundingClientRect();
  if(!(s.position==='fixed'||s.position==='sticky'||el.matches('dialog,[role="dialog"],[role="alertdialog"]'))) return false;
  if(r.width<=0||r.height<=0||r.right<=0||r.bottom<=0||r.left>=innerWidth||r.top>=innerHeight) return false;
  const text=(el.innerText||'').slice(0,6000);
  return /\bcookies?\b|файл[а-яё]*\s+cookie|soubory\s+cookie|soubory\s+cookies/i.test(text);
}
"""
CUSTOM_ACCEPT_TEXT = re.compile(
    r"^\s*(?:"+"|".join(re.escape(label) for label in sorted(ACCEPT))+r")[.!?]?\s*$",
    re.IGNORECASE,
)


def _custom_roots(frame, config):
    # Seed from exact accept labels, not arbitrary elements across the DOM.
    # Ordinary DOM ancestor walk; known-root path retains open shadow support.
    candidates=frame.locator("button,[role=button]").filter(has_text=CUSTOM_ACCEPT_TEXT)
    count=candidates.count()
    if count>MAX_ROOTS:
        return [],True
    roots=[]
    for i in range(count):
        candidate=candidates.nth(i)
        if not candidate.is_visible() or not candidate.evaluate(CONTROL_JS,timeout=500):
            continue
        ancestor=candidate
        for _ in range(6):
            ancestor=ancestor.locator("xpath=..")
            if ancestor.count()!=1:
                break
            if not ancestor.evaluate(CUSTOM_ROOT_JS,timeout=500) or not ancestor.is_visible():
                continue
            accept,accept_ambiguous=_controls(ancestor,config,"accept_all")
            reject,reject_ambiguous=_controls(ancestor,config,"reject_optional")
            if (accept or accept_ambiguous) and (reject or reject_ambiguous):
                roots.append(ancestor)
                if len(roots)>1:
                    return roots,True
                break
    return roots,False


def _roots(page, expected, config):
    selectors=list(ROOTS) if config.get("detect_automatically",True) else []
    if config.get("banner_selector"):
        # Explicit root overrides auto candidates (avoid nested CMP ambiguity).
        selectors=[config["banner_selector"]]
    if not selectors:
        return [],False
    result=[]
    for frame in page.frames[:MAX_FRAMES]:
        try:
            if origin(frame.url)!=expected:
                continue
        except ValueError:
            continue
        roots=frame.locator(",".join(selectors))
        count=roots.count()
        if count>MAX_ROOTS:
            return [],True
        for i in range(count):
            root=roots.nth(i)
            if root.is_visible() and root.evaluate(ROOT_JS,timeout=500):
                result.append(root)
                if len(result)>1:
                    return result,True
    if not result and config.get("detect_automatically",True) and not config.get("banner_selector"):
        for frame in page.frames[:MAX_FRAMES]:
            try:
                if origin(frame.url)!=expected:
                    continue
            except ValueError:
                continue
            roots,ambiguous=_custom_roots(frame,config)
            if ambiguous:
                return roots,True
            result.extend(roots)
            if len(result)>1:
                return result,True
    return result,False


def _matches_control(info, strategy):
    labels=ACCEPT if strategy=="accept_all" else NECESSARY if strategy=="necessary_only" else REJECT|NECESSARY
    return bool(info and (strategy=="manual_selector" or _normalize(info["label"]) in labels
                          or info["id"] in PROVIDER_IDS.get(strategy,set())))


def _controls(root, config, strategy):
    controls=root.locator(",".join(config["selectors"]) if strategy=="manual_selector"
                          else "button,[role=button],input[type=button]")
    count=controls.count()
    if count>MAX_CONTROLS:
        return [],True
    matches=[]
    for i in range(count):
        control=controls.nth(i)
        if not control.is_visible():
            continue
        info=control.evaluate(CONTROL_JS,timeout=500)
        if _matches_control(info,strategy):
            matches.append(control)
            if len(matches)>1:
                return matches,True
    return matches,False


def handle_cookie_consent(page, expected, config=None, cancelled=lambda:False):
    """Return evidence of dismissal, not proof of the vendor's consent storage.

    At most one real click, even if verification times out. No raw site text,
    cookies, URLs, or exception messages are written to consent metadata.
    """
    config=config or {}
    strategy=config.get("strategy","reject_optional")
    if not config.get("enabled",False) or strategy=="disabled":
        return {"status":"disabled","code":"disabled","strategy":strategy,"clicked":False}
    check_cancelled(cancelled)
    start=monotonic()
    deadline=start+config.get("timeout_ms",5000)/1000
    original_url=page.url
    navigation=[]
    same_document=[]
    requests=[]
    responses=[]
    popups=[]
    clicked=False
    detected=False

    def on_request(request):
        if request.is_navigation_request():
            try:
                main=request.frame==page.main_frame
            except Exception:
                return
            if main:
                requests.append(clicked and request.url==original_url and
                                request.method=="GET" and request.redirected_from is None)

    def on_response(response):
        request=response.request
        if request.is_navigation_request():
            try:
                main=request.frame==page.main_frame
            except Exception:
                return
            if main:
                responses.append(clicked and response.url==original_url and
                                 (200<=response.status<300 or response.status==304))

    # Chromium CDP distinguishes actual document commits from same-document
    # History API events, unlike Playwright's shared framenavigated event.
    cdp=None
    main_id=None

    def on_document(event):
        frame=event["frame"]
        if frame.get("id")==main_id or not frame.get("parentId"):
            navigation.append(clicked and frame.get("url")==original_url)

    def on_same_document(event):
        if event.get("frameId")==main_id:
            same_document.append(event.get("navigationType")=="historyApi" and
                                 event.get("url")==original_url)

    def on_popup(popup):
        popups.append(True)
        popup.close()

    def navigation_reason():
        if popups:
            return "popup"
        if page.url!=original_url:
            return "url_changed"
        if any(not item for item in same_document):
            return "same_document_url_or_type_changed"
        if any(not item for item in requests+navigation+responses):
            return "unexpected_navigation"
        if max(len(requests),len(navigation),len(responses))>1:
            return "repeated_navigation"
        if navigation and not requests:
            return "navigation_without_document_request"
        return None

    def changed():
        return navigation_reason() is not None

    def result(status,code):
        return {"status":status,"code":code,"strategy":strategy,
                "clicked":clicked,"detected":detected,
                "navigation":{"document_requests":len(requests),
                              "main_frame_events":len(navigation)+len(same_document),
                              "document_commits":len(navigation),
                              "same_document_events":len(same_document),
                              "same_url_history_events":sum(same_document),
                              "document_responses":len(responses),
                              "same_url_reload":bool(requests and navigation and responses
                                                     and not changed()),
                              "reason":navigation_reason(),
                              "phase":"after_click" if clicked else "before_click"},
                "elapsed_ms":int((monotonic()-start)*1000)}

    page.on("request",on_request)
    page.on("response",on_response)
    page.on("popup",on_popup)
    try:
        # Fail closed if navigation classification cannot be established.
        try:
            cdp=page.context.new_cdp_session(page)
            cdp.send("Page.enable")
            main_id=cdp.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
            cdp.on("Page.frameNavigated",on_document)
            cdp.on("Page.navigatedWithinDocument",on_same_document)
        except Exception:
            return result("failed","navigation_observer_unavailable")
        while remaining_ms(deadline)>0:
            check_cancelled(cancelled)
            if changed():
                return result("failed","navigation_changed")
            roots,ambiguous=_roots(page,expected,config)
            if ambiguous:
                detected=True
                return result("unresolved","ambiguous_banner")
            if roots:
                detected=True
                root=roots[0]
                matches,ambiguous=_controls(root,config,strategy)
                if ambiguous:
                    return result("unresolved","ambiguous_control")
                if matches and remaining_ms(deadline)>=350:
                    # Pin the actual element; never re-resolve a changed nth()
                    # locator during the action. Recheck safety at action time.
                    root_handle=root.element_handle(timeout=min(500,remaining_ms(deadline)))
                    handle=matches[0].element_handle(timeout=min(500,remaining_ms(deadline)))
                    check_cancelled(cancelled)
                    if changed():
                        return result("failed","navigation_changed")
                    if (root_handle is None or handle is None or
                            not _matches_control(handle.evaluate(CONTROL_JS),strategy)):
                        return result("unresolved","control_changed")
                    owner=handle.owner_frame()
                    if owner is None or origin(owner.url)!=expected:
                        return result("unresolved","control_changed")
                    if changed():
                        return result("failed","navigation_changed")
                    clicked=True
                    handle.click(timeout=max(1,min(1500,remaining_ms(deadline))),no_wait_after=True)
                    hidden_since=None
                    generation=None
                    while remaining_ms(deadline)>0:
                        check_cancelled(cancelled)
                        if changed():
                            return result("failed","navigation_changed")
                        current_generation=(len(requests),len(navigation),len(responses))
                        if current_generation!=generation:
                            hidden_since=None
                            generation=current_generation
                        # A permitted reload must have a successful document
                        # response and committed navigation before verification.
                        if requests and not (navigation and responses):
                            pause(page,deadline,cancelled,150)
                            continue
                        try:
                            ready=page.evaluate("() => document.readyState !== 'loading' && !!document.body")
                            visible,ambiguous=_roots(page,expected,config) if ready else ([],False)
                            # A custom overlay may lose its buttons while still
                            # covering the page. Verify the pinned original root
                            # too, unless a new document has replaced it.
                            old_root_visible=not navigation and root_handle.is_visible()
                        except Exception:
                            if changed():
                                return result("failed","navigation_changed")
                            if requests:
                                pause(page,deadline,cancelled,150)
                                continue
                            raise
                        if changed():
                            return result("failed","navigation_changed")
                        if current_generation!=(len(requests),len(navigation),len(responses)):
                            hidden_since=None
                            continue
                        if ready and not visible and not ambiguous and not old_root_visible:
                            if hidden_since is None:
                                hidden_since=monotonic()
                            elif monotonic()-hidden_since>=.6:
                                return result("dismissed","banner_hidden_after_reload" if requests else "banner_hidden")
                        else:
                            hidden_since=None
                        pause(page,deadline,cancelled,150)
                    if changed():
                        return result("failed","navigation_changed")
                    if requests and not (navigation and responses):
                        return result("failed","navigation_changed")
                    return result("unresolved","banner_still_visible" if hidden_since is None else "dismissal_unverified")
            pause(page,deadline,cancelled,200)
        return result("unresolved","requested_control_unavailable") if detected else result("not_detected","no_recognized_banner")
    except CaptureCancelled:
        raise
    except Exception as exc:
        if changed():
            return result("failed","navigation_changed")
        return result("failed","consent_timeout" if type(exc).__name__=="TimeoutError" else "consent_failed")
    finally:
        page.remove_listener("request",on_request)
        page.remove_listener("response",on_response)
        page.remove_listener("popup",on_popup)
        if cdp is not None:
            try:
                cdp.detach()
            except Exception:
                pass


def consent_unresolved(consent):
    return consent.get("status") in ("unresolved","failed")


def consent_quality(quality, consent):
    if consent_unresolved(consent) and quality.get("status")!="invalid":
        return dict(quality,status="warning",warnings=list(quality.get("warnings",[]))+["cookie_consent_"+consent["code"]])
    return quality
