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
