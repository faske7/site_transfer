# RE/MAX Delux production evidence feedback — PR-15

Sources: [Evidence audit](https://github.com/faske7/phuket_estate/blob/feat/remax-design-foundation/docs/EVIDENCE_AUDIT.md), [Missing evidence](https://github.com/faske7/phuket_estate/blob/feat/remax-design-foundation/docs/MISSING_EVIDENCE.md).

Reported 9 white PNGs of 39, all six home device images, white desktop contact image, incomplete lazy/reveal sections and overflow. The audit also reports six failed scroll states. The original PNG bytes were not independently inspected here.

Confirmed at base 67b40bbf8a205899376916c16b4251b226d960c6: baseline and device use fixed 700 ms after DOMContentLoaded. Baseline registers a file immediately after screenshot; device checks format and pixel count but not content. Neither traverses the page before capture. These mechanisms explain vulnerability to delayed hydration, not the precise site-side cause of each white frame. Explicit state capture has its own 700 ms delay and offline policy; unchanged in this increment except for PNG content validation.

PR-15 adds bounded readiness polling, document scroll, PNG validation, diagnostics and additive metadata. Invalid images are excluded from baseline/device evidence. No live reference recapture or claims of exact design completeness. Scope: capture reliability only; earlier Reference Kit v2 expansion is deferred.
