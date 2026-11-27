# Scroll Timeline (PR-15)

Opt-in evidence for scroll-driven design, not an animation reconstruction or video.
RE/MAX local user experiment: desktop balloon moves during scrolling, mobile
requires repeated scrolling to stable bottom; user reports both completed.
No raw local screenshots were supplied for independent inspection.

Example top-level configuration:

~~~json
"scroll_timeline": {
  "enabled": true,
  "routes": ["/"],
  "profiles": [
    {"viewport": "desktop", "step_px": 250, "settle_ms": 1500, "motion_tracking": true},
    {"viewport": "mobile", "step_px": 600, "settle_ms": 800, "motion_tracking": false}
  ],
  "max_frames": 150,
  "stable_steps": 5,
  "visual_threshold_percent": 0.5,
  "timeout_ms": 300000
}
~~~

At most two explicitly seeded route/viewport sequences per run. Fresh context,
normal public network guard, consent preflight, readiness and scroll-to-top.
Viewport PNGs with animation enabled; positive wheel steps, mobile scrollBy
fallback. Record actual geometry, sampled DOM hash/count, pixel difference
(12 intensity units per RGB channel; configurable changed-area threshold), and
optional sampled visible-node motion with normal vertical scroll compensation.
Motion samples capped at 40 changed nodes per frame, scan 5000 DOM elements /
500 visible elements, text used only for hash. Frame and diff PNGs hashed.
Pixel difference includes normal scrolling, not isolated balloon movement.

Stop after stable geometry and DOM on five consecutive comparisons (configurable)
and report bottom_reached only at actual bottom. A stall above bottom is partial.
Continuous animation is reported but not a termination veto; max frames,
96 MiB PNG/diff per sequence and cooperative time budget prevent unbounded work.
Invalid PNG halts sequence without publishing that frame. No claim of complete
motion trajectory if any bound or error occurs. Consent failed/unresolved stops
timeline; not_detected is not proof of absence. Per-frame checkpoints update
existing job manifest; no schema migration or new database. Existing 90-minute
worker hard limit and 512 MiB kit cap remain. Snapshot/PNG timing is approximate.

Evidence in scroll-timeline-manifest.json and scroll-timeline/<viewport>/<route hash>/.
Reference Kit includes only listed hashed frames and difference maps from selected
run, with manifest cross-check. TASK.md guides Codex to use timeline evidence.
No dedicated Studio gallery in this change; download kit to inspect. Existing
baseline/device/interaction outputs unchanged. New configs opt in; old configs
remain disabled. No raw asset redistribution or action beyond scrolling.
Tests authored; local and Docker acceptance pending.

PR-16 adds per-frame scroll_observation and scroll_geometry plus sequence scroll_intelligence. Measurable active axes determine end; transform-only end is unverified. Existing limits and paths unchanged. See SCROLL_INTELLIGENCE.md.

PR-17 adds optional sequence-level performance counters and reuses the decoded preceding frame. Raw PNG evidence and threshold semantics remain unchanged. See [performance design](SCROLL_PERFORMANCE.md).

Horizontal homepage evidence is supplemental: exact horizontal panorama when overlap is verified, and an independently derived chronological storyboard for dynamic scenes. Both are bounded by remaining sequence resources. See [Horizontal Homepage Capture](HORIZONTAL_HOMEPAGE_CAPTURE.md).
