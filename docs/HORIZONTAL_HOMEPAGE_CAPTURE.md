# Horizontal Homepage Capture

This scoped fix derives extra evidence from the existing opt-in Scroll Timeline.
Only route / and desktop / desktop_wide viewports of at least 600 CSS pixels are
eligible. Baseline full-page PNG, raw timeline frames, pixel difference maps,
mobile and other routes remain unchanged. No CSS rewrites, animation disabling,
network policy changes, extra browser pass or changes to scroll target semantics.

## Outputs
- horizontal-panorama.png: at most one exact horizontal strip per sequence.
  A stable direct clipping parent, pure integer horizontal translation,
  complete observed left-to-right coverage and nonuniform pixel-identical
  overlaps of at least 32 pixels are required. No synthesized pixels or resizing.
- horizontal-storyboard.png: independent chronological overview of at most
  eight original viewport states, separated by 8-pixel gutters. Useful for
  parallax, moving balloons and independently animated content, including when
  exact stitching fails. It is not a continuous panorama or complete trajectory.
  Prefer frames around observed horizontal motion; if no signal is established,
  label the overview horizontal_motion_unverified. All omitted overview frames
  remain in the original timeline.
- Each derived artifact has source indices/hashes, dimensions, method, and
  checksum in the timeline manifest and is included in Reference Kit. A failed
  derivation is recorded as unavailable, not an error in the underlying capture.

Both outputs are bounded individually by 16000 px width, 8 million pixels,
16 MiB PNG and the remaining existing 96 MiB per-sequence budget and deadline.
No increase to the 512 MiB kit cap. A depleted budget can prevent either output.
Only successful source screenshots are used.

## Configuration and limitations
Enable scroll_timeline on the explicitly seeded / route with the existing
desktop profile (motion_tracking true recommended). No new configuration keys.
The existing maximum of two route/viewport sequences remains; desktop + mobile
continues to work as before. To also obtain desktop_wide horizontal evidence,
run another capture with desktop_wide configured as one of the two timeline
profiles; do not silently replace the mobile sequence. A baseline screenshot
alone does not activate this feature. Real-site structure and motion may not
meet exact stitch conditions. The storyboard preserves sampled appearances,
not a flattened full-width recreation or all motion layers. No promise of
complete horizontal content beyond the actual captured frames.

## Acceptance
Run tests/test_horizontal_capture.py, tests/test_scroll_timeline.py,
tests/test_reference_kit.py, and the full pytest suite. Then rebuild Docker and
run the existing maximum-coverage RE/MAX configuration. Inspect
scroll-timeline-manifest.json and ZIP; compare baseline and original frame
dimensions and hashes, and inspect actual derived pixels. Repeat for wide
desktop if needed. Known interaction scroll_target_unreached on two desktop
views remains a separate deferred Adaptive Scroll Target Resolution task.
Tests authored; execution and production verification pending.
