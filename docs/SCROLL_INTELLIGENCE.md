# Logical PR-16 — Scroll Intelligence Engine

Stacked on PR-15 (b0031cf). Separate review/merge. Scope: scroll only.
User reported RE/MAX production run 27a2f5ec-4cb5-4272-b7a7-909b96d2d78b:
desktop 71 frames, Y=16079/16079; mobile 23 frames, Y=10196/10196; both
consent dismissed and bottom_reached, no timeline errors. Legacy interaction
scroll failed on desktop and desktop_wide. Overall capture and kit failed;
those failures are intentionally not addressed here. Actual balloon animation
and exact RE/MAX scroll implementation have not been independently inspected.

## Design

scroll_detection.py samples actual root x/y, extents, visible nested scroll
containers, and CSS transforms/individual transform properties/position offsets.
scroll_engine.py sends wheel input, uses geometry-based horizontal/nested retry
after stalls, and records observed displacement and transform candidates.
No fixed assumption that vertical wheel implies vertical visual movement.
Short idle sample excludes transforms already changing before input, but
correlation does not prove causality. A wheel-triggered transform can be
observed even when root Y remains zero. No pixel-only success.

Interaction Capture uses the shared engine, preserves fresh contexts and
the offline gate. Ordinary scroll_y remains a document target; failure to
reach it is explicit. For non-document movement target_reached is null and
quality warns that the target is not measurable. No arbitrary JS or new
actions; only the prior bounded mobile scrollBy fallback is retained.

Timeline uses the shared engine with existing frame, byte and time bounds.
Frame evidence includes root and container geometry, input axis, measured
progress and sampled transform observations; sequence summary lists modes
and actual observed axes. Stable bottom must include measurable active axes.
Transform-only endpoint is unverified, thus partial; a truly static,
non-scrollable sampled document can finish. Continuous autonomous animation
does not by itself establish scroll progress. Existing legacy evidence
and ZIP paths remain readable. Baseline smart_scroll remains separate because
its bounded preload-and-restore semantics differ from user scroll capture.

Limits: at most 5000 scanned DOM nodes, 32 visible nested scroll containers,
500 visible transform samples, 40 changed transform IDs per step; ordinary
DOM only, no cross-frame or closed shadow coverage, complex custom scroll
controllers/RTL writing modes may require further evidence. Candidate retries
are bounded; hidden/offscreen containers and page-wide simultaneous independent
scroll areas are not exhaustive. Sticky/layout movement without transform or
position style change may not be detected. No autoplay suppression or site
framework assumptions. Existing navigation, cancellation, public network
policies and offline interaction gate remain. No database migration,
worker-limit change, GUI gallery, expanded coverage or kit repair in this PR.

## Acceptance

Run targeted tests/test_scroll_intelligence.py, tests/test_interaction_capture.py,
tests/test_scroll_timeline.py, tests/test_cookie_consent.py and
tests/test_capture_quality.py, then full pytest. Synthetic fixtures include
vertical, horizontal, nested vertical/horizontal, transform-only, hybrid,
idle animation rejection and cancellation. Then real RE/MAX full production
test (maximum supported coverage, no reduced acceptance configuration).
Tests authored; not run on this remote editing surface. Keep draft.

PR-17 shares document candidates while preserving separate observations across input/idle/fallback. See [performance design](SCROLL_PERFORMANCE.md).

PR-18 follow-up supersedes the offline gate for isolated scroll only: guarded public GET/HEAD remains available for lazy resources, with main-frame navigation rejection and recognized crash-screen detection. Other interaction actions retain offline mode. Engine semantics and budgets unchanged. See INTERACTIONS.md.
