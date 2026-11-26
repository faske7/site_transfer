# Cookie consent preflight (PR-15)

Opt-in per immutable project configuration. Existing projects remain disabled.
Create a new project using the same routes, viewports and scenarios, adding:

~~~json
"browser": {
  "engine": "chromium",
  "headless": true,
  "timeout_ms": 30000,
  "cookie_consent": {
    "enabled": true,
    "strategy": "reject_optional",
    "timeout_ms": 5000,
    "detect_automatically": true
  }
}
~~~

Strategies: reject_optional (default when enabled), necessary_only, accept_all
(explicit opt-in only), manual_selector, disabled. No automatic fallback to
accept_all. Selectors are exact simple CSS ID/class/data-testid strings.
For manual_selector provide banner_selector and one to five selectors, and
review the root and control in the actual reference. Example:

~~~json
"cookie_consent": {
  "enabled": true,
  "strategy": "manual_selector",
  "detect_automatically": false,
  "banner_selector": "#cookie-banner",
  "selectors": ["#reject-cookies"],
  "timeout_ms": 5000
}
~~~

Automatic detection uses bounded known container selectors and exact normalized
button labels in English, Czech, German, French and Russian, plus selected
OneTrust/Cookiebot IDs. Other supported container candidates include CookieYes,
Usercentrics and consentmanager; vendor versions are not certified. Ambiguous
roots/buttons are not clicked. Open Shadow DOM via Playwright CSS locators and
same-origin frames (up to five total) are best effort; closed shadow roots and
cross-origin frame controls are unsupported. Only consent-marked visible roots,
safe button controls outside forms/links, at most one real click per context.
No storage injection, overlay removal, user identity, consent cookie values or
raw site error messages in reports. No change to GET/HEAD-only public proxy,
SSRF guard, WebSocket block or post-load interaction offline gate.

Runs before shared screenshot readiness, scrolling, measurement, asset
inventory and responsive probes; device contexts and interaction contexts
also run preflight separately. Interaction preflight is before offline gate.
The budget is 1–8s, default 5s, per context; existing job hard limit unchanged.
Cooperative deadline cannot preempt all synchronous browser operations.

Evidence statuses: disabled, not_detected (no recognized root; not proof of
absence), dismissed (recognized root no longer visible on two polls; not
proof of stored consent), unresolved, failed. Unresolved/failed are manifest
errors and screenshot warnings where evidence exists, so partial runs are
honest. Navigation/popup during handling fails the affected capture, except one observed successful non-redirected GET document reload of the exact original URL after the consent click. The reload must commit and return a successful document response before banner disappearance can be verified. URL changes (including hash/query), pre-click navigation, redirects, repeated reloads and popups remain rejected. No second click; original timeout remains. Sanitized navigation counts/reason/phase are recorded. Banner absence must persist for at least 600ms; later changes are still possible. Metadata
in capture_quality/artifacts, device and interaction entries, GUI and ZIP.
Legacy manifests remain readable. No migration.

Production RE/MAX actual selector and dismissal not yet verified; automatic
detection may miss custom CMPs. Review actual images even for dismissed.
No guarantee of vendor-specific preference persistence, tracking prevention,
late banners, nested dialogs or full visual completeness. Do not use the
feature for terms, login, payments or other non-cookie consent.

Fixture verification: synthetic multilingual HTML must declare UTF-8 both in the document and routed HTTP content type. On 8b32449, user regression returned 15 passed and 4 failures involving Czech controls. The fixture lacked both declarations; corrected fixture now asserts decoded Czech labels before testing the handler. Rerun pending, not a production validation.

After UTF-8 correction, targeted user run on 5fd5dc7: three Czech control tests passed, pipeline interaction still failed. The original test document had no visible content at scroll 600; split into positive colored content and negative blank viewport cases, requiring white PNG rejection and exclusion from partial ZIP. This tests rather than weakens the screenshot quality gate. Rerun pending.

Production follow-up: user stopped RE/MAX consent-enabled capture after widespread navigation_changed failures. Old metadata does not distinguish same-URL reload from other navigation; actual cause not yet proven. Added exact-URL reload support and six browser cases plus one full pipeline case. Retest pending.
