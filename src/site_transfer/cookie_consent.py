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
  if(!el.isConnected)return null;
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


def _paired_choices(root, config):
    accept,ambiguous_accept=_controls(root,config,"accept_all")
    reject,ambiguous_reject=_controls(root,config,"reject_optional")
    return bool((accept or ambiguous_accept) and (reject or ambiguous_reject))


def _custom_roots(frame, config):
    candidates=frame.locator("button,[role=button]").filter(has_text=CUSTOM_ACCEPT_TEXT).element_handles()
    if len(candidates)>MAX_ROOTS:
        return [],True
    roots=[]
    for candidate in candidates:
        if not candidate.is_visible() or not candidate.evaluate(CONTROL_JS):
            continue
        ancestor=candidate.evaluate_handle(
            "el => {const qualifies=("+CUSTOM_ROOT_JS+");"
            "for(let p=el.parentElement,i=0;p&&i<6;p=p.parentElement,i++){"
            "if(qualifies(p))return p;}return null;}"
        )
        root=ancestor.as_element()
        if root is None:
            ancestor.dispose()
            continue
        if root.is_visible() and _paired_choices(root,config):
            if not any(root.evaluate("(a,b)=>a===b",other) for other in roots):
                roots.append(root)
            if len(roots)>1:
                return roots,True
    return roots,False


def _roots(page, expected, config):
    selectors=list(ROOTS) if config.get("detect_automatically",True) else []
    explicit=config.get("banner_selector")
    if explicit:
        selectors=[explicit]
    if not selectors:
        return [],False
    result=[]
    frames=[]
    for frame in page.frames[:MAX_FRAMES]:
        try:
            if origin(frame.url)==expected:
                frames.append(frame)
        except ValueError:
            continue
    for frame in frames:
        roots=frame.locator(",".join(selectors)).element_handles()
        if len(roots)>MAX_ROOTS:
            return [],True
        for root in roots:
            if not root.is_visible():
                continue
            # Explicitly reviewed selector may identify an unnamed overlay
            # even if its prose lacks a recognized cookie keyword. Require
            # opposing exact choices and actual overlay positioning instead.
            marked=root.evaluate(ROOT_JS)
            reviewed=(explicit and config.get("strategy")!="manual_selector" and
                      root.evaluate("""el => el.isConnected &&
                          (['fixed','sticky'].includes(getComputedStyle(el).position) ||
                           el.matches('dialog,[role=dialog],[role=alertdialog]'))""")
                      and _paired_choices(root,config))
            if marked or reviewed:
                result.append(root)
                if len(result)>1:
                    return result,True
    if not result and config.get("detect_automatically",True) and not explicit:
        for frame in frames:
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
    controls=root.query_selector_all(",".join(config["selectors"]) if strategy=="manual_selector"
                                     else "button,[role=button],input[type=button]")
    if len(controls)>MAX_CONTROLS:
        return [],True
    matches=[]
    for control in controls:
        if control.is_visible() and _matches_control(control.evaluate(CONTROL_JS),strategy):
            matches.append(control)
            if len(matches)>1:
                return matches,True
    return matches,False


def _transient(exc):
    return type(exc).__name__=="TimeoutError" or any(
        marker in str(exc).lower() for marker in (
            "execution context was destroyed", "cannot find context", "cannot find object",
            "frame was detached", "frame has been detached", "element is not attached",
            "node is detached", "node is not attached",
        ))


def _within(root,control):
    return root.evaluate("""(root,el)=>{
        if(!root.isConnected||!el.isConnected)return false;
        for(let n=el;n;n=n.parentElement||n.getRootNode()?.host||null)
            if(n===root)return true;
        return false;
    }""",control)


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
    click_completed=False
    stage="observer"
    transient_retries=0
    scan_complete=False

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
                "click_completed":click_completed,"stage":stage,"transient_retries":transient_retries,
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
            try:
                stage="root_detection"
                scan_complete=False
                roots,ambiguous=_roots(page,expected,config)
                scan_complete=True
                if ambiguous:
                    detected=True
                    return result("unresolved","ambiguous_banner")
                if roots:
                    detected=True
                    root_handle=roots[0]
                    stage="control_detection"
                    matches,ambiguous=_controls(root_handle,config,strategy)
                    if ambiguous:
                        return result("unresolved","ambiguous_control")
                    if matches:
                        stage="control_recheck"
                        handle=matches[0]
                        owner=handle.owner_frame()
                        if (owner is not None and origin(owner.url)==expected and
                            root_handle.is_visible() and handle.is_visible() and
                            _within(root_handle,handle) and
                            _matches_control(handle.evaluate(CONTROL_JS),strategy)):
                            if remaining_ms(deadline)<350:
                                return result("unresolved","consent_budget_exhausted")
                            break
            except CaptureCancelled:
                raise
            except Exception as exc:
                if changed():
                    return result("failed","navigation_changed")
                if not _transient(exc):
                    raise
                transient_retries+=1
                scan_complete=False
            pause(page,deadline,cancelled,200)
        else:
            if not scan_complete:
                return result("failed","consent_detection_incomplete")
            return result("unresolved","requested_control_unavailable") if detected else result("not_detected","no_recognized_banner")

        check_cancelled(cancelled)
        if changed():
            return result("failed","navigation_changed")
        stage="click"
        clicked=True
        handle.click(timeout=max(1,min(5000,remaining_ms(deadline))),no_wait_after=True)
        click_completed=True
        deadline=max(deadline,monotonic()+1.5)
        stage="verification"
        hidden_since=None
        generation=None
        verification_complete=False
        while remaining_ms(deadline)>0:
            check_cancelled(cancelled)
            if changed():
                return result("failed","navigation_changed")
            current_generation=(len(requests),len(navigation),len(responses))
            if current_generation!=generation:
                hidden_since=None
                generation=current_generation
            if requests and not (navigation and responses):
                pause(page,deadline,cancelled,150)
                continue
            try:
                verification_complete=False
                ready=page.evaluate("() => document.readyState !== 'loading' && !!document.body")
                visible,ambiguous=_roots(page,expected,config) if ready else ([],False)
                old_root_visible=not navigation and root_handle.is_visible()
                verification_complete=True
            except CaptureCancelled:
                raise
            except Exception as exc:
                if changed():
                    return result("failed","navigation_changed")
                if not (requests or _transient(exc)):
                    raise
                transient_retries+=1
                hidden_since=None
                pause(page,deadline,cancelled,150)
                continue
            if changed():
                return result("failed","navigation_changed")
            if current_generation!=(len(requests),len(navigation),len(responses)):
                hidden_since=None
                continue
            if ready and not visible and not ambiguous and not old_root_visible:
                if hidden_since is None:
                    hidden_since=monotonic()
                elif monotonic()-hidden_since>=.6:
                    stage="complete"
                    return result("dismissed","banner_hidden_after_reload" if requests else "banner_hidden")
            else:
                hidden_since=None
            pause(page,deadline,cancelled,150)
        if changed() or (requests and not (navigation and responses)):
            return result("failed","navigation_changed")
        if not verification_complete:
            return result("unresolved","dismissal_unverified")
        return result("unresolved","banner_still_visible" if hidden_since is None else "dismissal_unverified")
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
