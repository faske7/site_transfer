# PR-13 — Advanced interaction capture

Explicit opt-in per project. Import a JSON config (existing projects are immutable; create a new project for a changed config). Default projects retain baseline screenshots and legacy bounded hover-only design observations; no unrequested clicks.

Example: adapt the placeholders to a trusted, authorized reference and actual selectors.

```json
{
  "source": {
    "url": "https://example.com",
    "pages": [
      "/"
    ]
  },
  "target": {
    "project_name": "state_demo",
    "backend": "Django",
    "frontend": "JavaScript"
  },
  "discovery": {
    "enabled": false,
    "max_pages": 1
  },
  "interactions": {
    "enabled": true,
    "scenarios": [
      {
        "id": "menu-open",
        "route": "/",
        "action": "click",
        "selector": "#menu-toggle",
        "expect_visible": "#menu-panel"
      },
      {
        "id": "modal-open",
        "route": "/",
        "action": "click",
        "selector": "#modal-toggle",
        "expect_visible": "#modal"
      },
      {
        "id": "hover-nav",
        "route": "/",
        "action": "hover",
        "selector": ".nav-link",
        "viewports": [
          "desktop"
        ]
      },
      {
        "id": "focus-menu",
        "route": "/",
        "action": "focus",
        "selector": "#menu-toggle"
      },
      {
        "id": "accordion-open",
        "route": "/",
        "action": "click",
        "selector": "#accordion-summary",
        "expect_visible": "#accordion-content"
      },
      {
        "id": "scrolled-header",
        "route": "/",
        "action": "scroll",
        "scroll_y": 600
      }
    ]
  }
}
```

Supported: 12 distinct scenario IDs per project, up to 4 configured viewports, max 48 state attempts; route must match an explicit seed within the capture limit; simple unique CSS ID, class or data-testid selector; one action per fresh context; wait 0–1500 ms; scroll 1–10000 px. Desktop click, mobile tap (<600 CSS px); hover unavailable on touch-only viewport. Optional visibility assertion proves only that exactly one matching element was visible after action. No typing, arbitrary JS, form submission, authenticated session, multistep sequence, iframe/shadow DOM targeting, automatic click discovery or dynamic network-driven states.

Initial page load uses normal public proxy restrictions. After initial load, the interaction context blocks further routed requests and switches offline, rejects link/form controls and known destructive labels, permits explicit buttons outside forms, native details summary and semantically marked ARIA buttons. Navigation/popup detection and guards are defense in depth, not proof that arbitrary site code is safe. A page may have side effects during initial GET, already in-flight requests or local script; only trusted authorized sites and explicitly reviewed controls. Do not target payment, purchase, delete, authentication, data mutation or consent controls in explicit interaction scenarios. An independent opt-in cookie-consent preflight may dismiss a recognized banner before the offline gate; see COOKIE_CONSENT.md. No change to existing proxy's documented HTTPS redirect/egress limitations.

Each attempted state has id, route, viewport, action, status, optional before/after style and scroll evidence, expectation flag, blocked request count, baseline_index and viewport PNG SHA256. A captured screenshot is not semantic success unless supported by the observation or explicit expectation. Failed/skipped states contribute errors and a partial run when baseline exists. Pending states remain not_attempted in interrupted runs; old runs never rewritten. Separate interaction-manifest.json and interactions/<viewport>/<id>.png; no changes to baseline artifact indexes or comparison algorithm. Reference Kit includes only captured state images and hashed report. API checks registered paths and hashes; GUI displays gaps.

Test locally: python -m pip install -e '.[dev,server,capture]' ; python -m playwright install chromium ; python -m pytest -v. Frontend npm ci, npm run test, npm run build. Rebuild Docker (finish jobs and close old app before replacing runtime), create a project using authorized real selectors, run pipeline, check baseline plus separate states, JSON, ZIP content and hashes, skipped unsafe targets, persistence, old runs and unchanged baseline comparison. Rebuild desktop after accepting PR. No schema migration. Tests and manual acceptance pending.

PR-15 reliability follow-up: initial readiness polling is bounded to 5s after navigation before closing the same offline gate. For scroll states it checks that the document can scroll. Failure stage/code, readiness, elapsed time and blocked request counts are recorded. The single declared action is never automatically repeated; screenshot timeout is 8s, and invalid PNGs are not registered. Captured states may warn of blocked resources or unsettled readiness. Existing network restrictions remain unchanged.

PR-16 scroll states use bounded wheel steps through ScrollEngine. Offline gate unchanged. Exact document Y target required when document Y moves; other observed scroll modes carry target_reached=null and a quality warning. See SCROLL_INTELLIGENCE.md.

## PR-18 — guarded scroll lazy loading
Supersedes the earlier blanket offline rule for scroll only. After consent/readiness, scroll keeps the existing guarded public GET/HEAD network transport, rejects main-frame navigation requests, retains popup/navigation checks and submit/click protection. Click, hover and focus remain offline. Reports include network_mode (guarded_scroll or offline). Recognizable short top-level Next.js client-side application error screens fail with application_crash; console noise and iframe text alone do not trigger this heuristic. It is not a universal application health detector. GET requests can have side effects; trusted authorized references only, existing proxy limitations apply. No coordinate or action-budget changes. Regression tests and real capture acceptance pending.
