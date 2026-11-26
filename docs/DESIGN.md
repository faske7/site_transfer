# PR-05 Design Intelligence

Run a new authorized reference capture in Studio after rebuilding. No extra navigation is required for design analysis; computed styles are collected before the baseline screenshot; bounded hover observations occur after that screenshot. Older captures are not rewritten.

Per run: design/<viewport>/<route>.json contains sampled elements, measured page coordinates, computed layout/typography/colors, observed animations, accessible media rules/keyframes and hover observations. design-tokens.json aggregates the top sampled values by frequency and groups responsive observations by URL and viewport. Values are observations, not inferred design-system definitions.

Limits: max 350 visible-layout elements from 3000 visited DOM nodes, 3000 CSS rules, 100 stylesheets, 60 animations/keyframes, 12 interaction candidates and four desktop hover attempts per route/viewport. Cross-origin stylesheet CSSOM may be inaccessible; counts/limits are recorded. No clicks, forms, focus, touch, interaction screenshots, menu/modal state automation, iframe/shadow DOM traversal, font asset retrieval or exact inferred breakpoints. Motion is a point-in-time sample and CSS timing, not a frame-by-frame recording. No claims of exhaustive design analysis. Baseline screenshots remain separate and unchanged. Design failures enter the capture error list without dropping successful baseline screenshots. Respect the existing trusted-public-target restriction.

To disable design measurements or interaction probes use the existing measurements.enabled and interactions.enabled configuration fields. If both false, no design JSON is generated.

Verification:
- python -m pip install -e '.[dev,server,capture]'
- python -m pytest -v (browser fixture skips if Chromium not installed)
- docker compose up -d --build --wait
- Create a new capture for an authorized reference; verify baseline screenshots, per-viewport JSON reports and aggregate tokens in the GUI.
- Inspect actual font/color/spacing values against a known page; inspect history from PR-04 and repeat capture.
- Optional: run the offline browser fixture in a test environment with Chromium installed (`python -m playwright install chromium`).

PR-13 adds separate opt-in visual state screenshots; the legacy bounded hover observations above remain unchanged. See [interaction capture](INTERACTIONS.md).

## PR-14 — Advanced Design Intelligence (v2)

New reports retain legacy fields and add `summary.advanced` with observed CSS pixel lengths, RGBA palette (integer sRGB channels only), normalized timing in milliseconds (computed CSS, not playback), bounded headings, container hierarchy and DOM semantic metadata. No raw accessible labels or input values collected. Counts are property occurrences, not a reconstructed design system. Unsupported values remain in raw styles. Accessibility metadata is not an audit. `schemas/design-report.schema.json` mirrors the packaged structural schema used when writing reports. Tokens JSON v2 indexes advanced reports while retaining existing token and responsive fields. Old reports and comparisons remain readable.

Responsive probes: after baseline screenshot and legacy hover observations, resize the first desktop-width context per route (width >=600) at 390/768/1024/1440/1920 CSS px, first ten routes only, 24 sampled positional selectors and 100 declared media queries, no added screenshots or navigation by the engine. Existing context is switched offline, then discarded; this is sequential width-only observation, not device emulation, not exact breakpoint inference. Failed or missing probes explicitly recorded; failed probe makes capture partial. All evidence exported via existing Reference Kit. Structural comparison checks additional shared computed CSS fields; actual cross-project GUI verification pending.

Acceptance: run pytest including real Chromium fixture and full capture pipeline regression with and without scenarios; npm ci/test/build; rebuild Docker, new capture on authorized site, verify v2 JSON and five desktop probes, old report access, interaction states, ZIP, comparison across two projects and restart persistence. No DB migration. Tests and manual acceptance pending.

### Device emulation and declared breakpoints (PR-14 extension)
Six fixed profiles: iPhone 13 390x844 DPR3, Pixel 7 412x915 DPR2.625, iPad 768x1024 DPR2, Laptop 1366x768 DPR1, Desktop 1440x900 DPR1, Full HD 1920x1080 DPR1. Fresh Chromium contexts before navigation, screen/viewport, UA, mobile/touch/DPR; Apple-shaped profiles do not simulate Safari. Fixed viewport heights intentionally differ from default Playwright browser chrome. Device evidence defaults on when measurements are enabled, first three routes (18 captures); set measurements.device_emulation.enabled=false to disable or max_routes=1..5 at project import. Existing immutable configs use defaults. CSS-scale PNG, bounded full-page or explicit viewport fallback; report records actual observed dimensions/DPR/UA and design evidence. Separate devices/ and device-manifest.json, verified hash, GUI and ZIP. No baseline index or interaction scenario changes. Existing proxy policy remains, no arbitrary network settings.

Responsive probes additionally test up to four simple declared integer px min/max-width conditions at threshold-1, threshold, threshold+1 (deduplicated with the five normal widths). Store actual media matches and changed sampled layout properties; no inferred breakpoints or separate boundary images. AX tree, CPU/network throttling and real Safari testing deferred. Full device captures add navigation and storage cost; max 30 profile attempts, existing 30-minute job and 512 MiB kit limits apply. Tests and manual acceptance pending.
