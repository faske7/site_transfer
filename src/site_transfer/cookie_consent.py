"""Opt-in, bounded cookie-banner interaction before reference capture.

No injected consent cookies, CSS hiding, arbitrary scripts, form submission,
cross-origin frame actions, or changes to the public browser network policy.
"""
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
    "souhlasím se všemi cookies", "souhlasím", "přijmout cookies",
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
    return result,False


def _controls(root, config, strategy):
    controls=root.locator(",".join(config["selectors"]) if strategy=="manual_selector"
                          else "button,[role=button],input[type=button]")
    count=controls.count()
    if count>MAX_CONTROLS:
        return [],True
    matches=[]
    labels=ACCEPT if strategy=="accept_all" else NECESSARY if strategy=="necessary_only" else REJECT|NECESSARY
    for i in range(count):
        control=controls.nth(i)
        if not control.is_visible():
            continue
        info=control.evaluate(CONTROL_JS,timeout=500)
        if not info:
            continue
        if strategy=="manual_selector" or _normalize(info["label"]) in labels or info["id"] in PROVIDER_IDS.get(strategy,set()):
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
    popups=[]
    clicked=False
    detected=False

    def on_navigation(frame):
        if frame==page.main_frame:
            navigation.append(True)

    def on_popup(popup):
        popups.append(True)
        popup.close()

    def changed():
        return bool(navigation or popups or page.url!=original_url)

    def result(status,code):
        return {"status":status,"code":code,"strategy":strategy,
                "clicked":clicked,"detected":detected,
                "elapsed_ms":int((monotonic()-start)*1000)}

    page.on("framenavigated",on_navigation)
    page.on("popup",on_popup)
    try:
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
                    handle=matches[0].element_handle(timeout=min(500,remaining_ms(deadline)))
                    check_cancelled(cancelled)
                    if changed():
                        return result("failed","navigation_changed")
                    if handle is None or not handle.evaluate(CONTROL_JS):
                        return result("unresolved","control_changed")
                    clicked=True
                    handle.click(timeout=max(1,min(1500,remaining_ms(deadline))))
                    while remaining_ms(deadline)>0:
                        check_cancelled(cancelled)
                        if changed():
                            return result("failed","navigation_changed")
                        visible,ambiguous=_roots(page,expected,config)
                        if not visible and not ambiguous:
                            # Allow one more poll to detect a replacement dialog.
                            pause(page,deadline,cancelled,200)
                            visible,ambiguous=_roots(page,expected,config)
                            if changed():
                                return result("failed","navigation_changed")
                            if not visible and not ambiguous:
                                return result("dismissed","banner_hidden")
                        pause(page,deadline,cancelled,150)
                    return result("unresolved","banner_still_visible")
            pause(page,deadline,cancelled,200)
        return result("unresolved","requested_control_unavailable") if detected else result("not_detected","no_recognized_banner")
    except CaptureCancelled:
        raise
    except Exception as exc:
        if changed():
            return result("failed","navigation_changed")
        return result("failed","consent_timeout" if type(exc).__name__=="TimeoutError" else "consent_failed")
    finally:
        page.remove_listener("framenavigated",on_navigation)
        page.remove_listener("popup",on_popup)


def consent_unresolved(consent):
    return consent.get("status") in ("unresolved","failed")


def consent_quality(quality, consent):
    if consent_unresolved(consent) and quality.get("status")!="invalid":
        return dict(quality,status="warning",warnings=list(quality.get("warnings",[]))+["cookie_consent_"+consent["code"]])
    return quality
