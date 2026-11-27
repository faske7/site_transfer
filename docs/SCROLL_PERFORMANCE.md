# PR-17 — Scroll Intelligence Performance Optimization

Stacked on PR-16 at d2c438be784da32dea9764c5c68898be4e6dc08e. No change to wheel/hover/idle/fallback ordering, endpoint classification, frame limits, settle intervals, security policy, original PNG storage or Reference Kit paths.

## Architecture
- A document-owned candidate cache retains the first 5000 body descendants in DOM order and the exact total count. MutationObserver childList/subtree invalidation drops strong references, including on body replacement, reparenting and hydration. takeRecords handles changes in the same JS task. Attribute/style changes do not invalidate membership; current geometry and styles are read again.
- Scroll Detection and Timeline share candidates, not observations. Separate ID WeakMaps preserve their existing identities. Each evaluate reads actual bounding rectangles before styles and transform fields; viewport predicates and truncation retain their previous semantics. No asynchronous IntersectionObserver exclusion, since transformed nodes may enter the viewport between callbacks.
- Reuse nested scroll extents and styles within a snapshot; read document height once per timeline snapshot. Geometry for independent observations must remain fresh. No cross-action geometry cache.
- PixelDiffSequence retains one fully decoded RGB predecessor and uses Pillow native difference, channel maximum, LUT threshold and binary-mask paste. Original PNG bytes are still published and hashed. Keep threshold 12 (strict greater-than), percent rounding, dimensions and RGB overlay colors. The standalone visual_diff interface remains available.
- The optional additive performance object aggregates counts and timings in timeline entries and explicit scroll observations. geometry_reads counts rectangle calls and scalar scroll/client reads, not layout flushes. visible_elements_sampled counts visible eligible elements, potentially above the transform sample cap. dom_full_scans counts candidate list rebuilds, not browser-internal traversals. png_decode_ms is included in pixel_diff_ms, not added again. total_processing_ms is measured component time, not total capture elapsed; excludes waits, screenshots, checkpoint I/O and uninstrumented work. peak_memory is Python process lifetime high-water RSS in bytes (or null), not per-sequence or browser peak.
- Context closure and pagehide release document state; explicit best-effort disconnect during capture teardown. Decoded images are closed on success, error and cancellation. No new dependency or database migration.

## Limitations
Large stable DOM still needs fresh geometry for correctness. The original bounded sampling and autonomous motion heuristics remain; no exhaustive hidden, cross-frame or shadow-tree coverage. The full production benchmark and leak verification remain acceptance gates. Compression-byte identity of overlays is not asserted; actual overlay bytes are registered and hashed.

See SCROLL_PERFORMANCE_BENCHMARK.md. Keep draft until parent PRs and regression/production acceptance are complete.
