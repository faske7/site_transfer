# Site Transfer Studio — implementation roadmap

## Objective
Convert an authorized reference site into a reproducible evidence package and concise Codex task. Capture important desktop/mobile routes and states upstream, so implementation agents reuse evidence instead of repeating browser work.

## Architecture
- Independent Python core in src/site_transfer; CLI and API share the same validation, capture and pipeline services.
- Local-first Docker Compose runtime: FastAPI, PostgreSQL, Redis, Celery worker, persistent artifact storage.
- React + TypeScript + Vite web interface, served through one localhost origin; API versioned under /api/v1.
- Playwright Chromium runs in a worker, not in the frontend or Tauri webview.
- macOS Tauri 2 shell is a required final deliverable; it reuses the frontend and manages the Compose lifecycle through constrained Rust commands. Docker Engine/Compose remains a prerequisite.
- Native arm64 on Apple Silicon; avoid amd64 emulation as a default. Keep the runtime usable on Linux/VPS. Remote access requires a separate authenticated deployment configuration.
- Store project metadata/job state in PostgreSQL, queue messages in Redis, evidence in durable storage; Redis is not the authoritative project record.
- Do not mount the host Docker socket into the API or worker. Expose local service ports on loopback only; no unauthenticated remote deployment.

## PR-01 — Foundation
JSON schema, independent CLI, validate/plan/init/validate-project, mandatory root CONTEXT.md and AGENTS.md. No browser operations.

## PR-02 — Docker & Backend API
Compose, FastAPI API, PostgreSQL project registry, Redis/Celery runtime, durable volumes, health checks, native-arm64-compatible dependencies. Establish basic project CRUD scope (create/list/read), config validation and API tests. Browser pipeline remains deferred.

## PR-03 — Web GUI
React/TypeScript dashboard, create/import projects, configure reference and target, list projects, view service status and prepare job/progress screens. Same frontend must be reusable by Tauri; do not embed hard-coded host URLs. Do not simulate successful jobs.

## PR-04 — Browser & screenshot capture
browser.py, discovery.py, capture.py: Playwright Chromium, bounded same-origin route discovery, desktop/mobile screenshots, explicit errors, evidence under design/reference/screenshots/. Add worker execution and job records. Restrict navigation/redirects and private-network access for untrusted URLs; never bypass access controls.

## PR-05 — Design intelligence
interactions.py, measurements.py, typography.py, motion.py: relevant interaction states, dimensions, breakpoints, typography and observed motion timing. Never invent missing measurements.

## PR-06 — Assets & reference kit
assets.py, manifest.py: asset inventory, provenance/licensing notes, hashes and evidence paths. Generate compact TASK.md, maintain CONTEXT.md and provide a downloadable/portable reference bundle. Only redistribute authorized assets.

## PR-07 — Visual comparison
comparison.py: viewport-matched screenshots, pixel/structural comparison, reproducible diff and documented thresholds; GUI before/after inspection.

## PR-08 — Pipeline & GitHub
pipeline.py, github.py: end-to-end jobs and CLI commands, durable checkpoints/resume, bounded retries, cancellation, job progress/logs, and reviewed publication. Use gh CLI or explicitly configured credentials with secret storage; never put tokens in project JSON. Generate Codex task, publish on a branch/PR only after explicit review. Report real failures.

## PR-09 — macOS desktop (mandatory)
Tauri 2 + existing React frontend; native arm64 Site Transfer.app and DMG. Detect installed Docker/Compose, provide actionable startup errors, start/check/stop only this application's services with explicit confirmation where appropriate, open project folders and display service/job status. Use bundled versioned Compose resources and stable application-data paths; preserve volumes on restart and upgrade. Restrict native command capabilities, avoid arbitrary shell execution, use a loopback API with origin/host protections and a secure desktop connection strategy. Test on Apple Silicon: first launch, restart, unavailable Docker, occupied port, data persistence, upgrade and uninstall behavior. Personal-use build is required; signing/notarization for public distribution is a separate release requirement. Do not ship a Docker-free version in this roadmap.

## Artifact contract
Generated target root: README.md, AGENTS.md, CONTEXT.md, TASK.md.
Reference evidence: design/reference/screenshots/ plus route, measurement, interaction and asset manifests.
Use supplied evidence first; capture only missing evidence and identify gaps. Every generated project must include and maintain CONTEXT.md.

## Scope and safety
Only authorized reference access; respect site boundaries, rate limits, privacy and licensing. Never bypass authentication or access controls. Reference design does not authorize redistribution of protected branding/assets.
