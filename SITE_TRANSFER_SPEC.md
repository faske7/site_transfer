# Site Transfer — implementation roadmap

## Objective
Convert an authorized public reference site into a reproducible evidence package and concise coding-agent task. Capture reference pages and important desktop/mobile states upstream so the implementation agent can reuse the evidence.

## PR-01 — Foundation
JSON configuration schema, package/CLI, validate and plan commands, documentation initialization and validation. Mandatory root CONTEXT.md and AGENTS.md. No browser operations.

## PR-02 — Browser & capture
browser.py, discovery.py, capture.py: Playwright Chromium, bounded same-origin route discovery, desktop/mobile full-page screenshots and explicit capture errors. Store evidence under design/reference/screenshots/.

## PR-03 — Design intelligence
interactions.py, measurements.py, typography.py, motion.py: relevant interaction states, dimensions, breakpoints, typography and observed animation timing. Never invent missing measurements.

## PR-04 — Assets & manifest
assets.py, manifest.py: asset inventory, licensing/provenance notes, hashes and evidence paths. Generate compact TASK.md and maintain CONTEXT.md.

## PR-05 — Visual comparison
comparison.py: viewport-matched screenshots, pixel and structural comparison, reproducible visual diff and documented thresholds.

## PR-06 — Pipeline & GitHub
pipeline.py, github.py: capture, verify, publish and run commands, checkpoint/resume and bounded retries. Authenticate with gh CLI, review changes before publishing; do not store tokens in configuration. Report failures without disguising them as success.

## Artifact contract
Generated target root: README.md, AGENTS.md, CONTEXT.md, TASK.md.
Reference evidence: design/reference/screenshots/ plus future route, measurement, interaction and asset manifests.
Future implementations should use the artifacts first, capture only missing evidence and explicitly identify gaps.

## Scope and safety
Only authorized reference access; respect site boundaries, rate limits, privacy and licensing. Never bypass authentication or access controls. Reference design does not authorize redistribution of protected branding/assets.
