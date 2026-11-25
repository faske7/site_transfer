# Project context — Site Transfer Studio

## Purpose
Build a local-first website reference analysis platform that hands an implementation-ready evidence package to Codex, reducing repeated browser work and token usage. Deliver CLI, Web GUI and a mandatory macOS desktop application.

## Architecture
src/site_transfer remains independent of the API and UI. PR-01 implements config, documentation, validation and CLI. PR-02 adds optional server adapters under src/site_transfer/server; Docker Compose manages FastAPI, PostgreSQL, Redis and Celery. PR-03 adds React UI under frontend/; FastAPI serves the built static files at the same origin. Future Tauri shell reuses the UI through an isolated API transport. See SITE_TRANSFER_SPEC.md for the approved nine-stage roadmap.

## Technology stack
Implemented: Python 3.11+, setuptools, JSON Schema Draft 2020-12, Jinja2, pytest.
PR-02 implementation: FastAPI, PostgreSQL 17, Redis 7, Celery and Docker Compose. PR-03 implementation: React 19, TypeScript, Vite, Vitest, Node 22 build stage. PR-04 adds Playwright Chromium 1.56.0. Planned: Tauri 2/Rust. PR-02 native arm64 runtime was verified by user.

## Important files
- pyproject.toml: dependencies and CLI entry point.
- schemas/transfer.schema.json: public config schema.
- templates/: public documentation templates.
- src/site_transfer/resources/: packaged mirrors; tests enforce parity.
- examples/remaxdelux.json: synthetic sample configuration.
- SITE_TRANSFER_SPEC.md: approved architecture and PR sequence.
- compose.yaml, Dockerfile, docs/DOCKER.md: local runtime.
- src/site_transfer/server/: API, registry, migration and worker.
- frontend/: shared Studio GUI and API client.
- docs/GUI.md: GUI build and acceptance checks.
- browser.py, discovery.py, capture.py: core capture engine.
- server/jobs.py, server/storage.py: capture persistence and artifact access.
- docs/CAPTURE.md: capture setup and limitations.
- measurements.py, typography.py, colors.py, motion.py, interactions.py, responsive.py, design_tokens.py: sampled design evidence.
- docs/DESIGN.md: PR-05 limits and verification.
- assets.py, manifest.py: inventory and portable kit.
- docs/REFERENCE_KIT.md: PR-06 contract and limits.

## Development commands
- python -m pip install -e '.[dev]'
- python -m pytest
- site-transfer validate examples/remaxdelux.json
- site-transfer plan examples/remaxdelux.json
- python -m pip install -e '.[dev,server]'
- docker compose config --quiet
- docker compose up -d --build
- curl -fsS http://localhost:8080/health/ready
- cd frontend && npm install && npm run test && npm run build
- open http://localhost:8080 (Docker GUI; use configured port)

## Current status
PR-01 merged into main (25d2b459); user verified all 14 foundation tests on macOS, Python 3.13.7, pytest 9.2.0 (0.70 s). PR-02 integration PR #3 merged into main (fb1afbcd). User verified 20/20 Python tests (5.25 s; one Starlette TestClient deprecation warning), native linux/aarch64 Docker, all five services, API create/list, generated documents, Celery ping and persistence after restart. The last three checks were confirmed by the user without raw logs. Create/list/read project registry generates mandatory documents before saving metadata. PR-04 adds Celery capture tasks with PostgreSQL job state and per-run artifacts. PR-03 Docker build and GUI launch succeeded according to the user; all six manual GUI acceptance checks passed (existing project, creation, validation, import, details, readiness). Standalone Vitest results and npm lockfile are not supplied. PR-03 merged into main (b11b7592) on user approval. PR-04: user confirmed local tests passed and an actual capture completed with two desktop/mobile screenshots. Exact test counts and raw logs were not supplied. User confirmed repeat-run isolation, gallery history and persistence after restart; PR #5 merged into main (d384499). PR-05 adds design evidence during the same capture pass. Local macOS Python 3.13.7 / pytest 9.2.0: 36 passed, 1 skipped (Chromium not installed locally), 1 Starlette warning, 5.19 s. User confirmed all six GUI checks: completed capture, desktop/mobile screenshots, two design reports, tokens JSON opens with typography/colors/spacing/responsive, prior history preserved. Standalone browser fixture not verified. PR-05 merged into main (4031690) on user approval. PR-06 adds inventory-only assets and portable selected-run ZIP export. User supplied local test output: 45 passed, 1 skipped (local Chromium unavailable), no failures shown. All nine new tests passed. User confirmed six manual GUI acceptance checks (completed capture, inventory, ZIP download, mandatory documents, screenshot/JSON evidence, prior-run export) and explicitly approved merge.

## Technical decisions
- Root CONTEXT.md is mandatory for this repository and every generated project.
- Capture reference evidence upstream and provide it to Codex.
- Keep CLI independent; API and UI must not duplicate core logic.
- Local-first loopback runtime; no Docker socket in server containers.
- Tauri manages Docker lifecycle on the host; Docker remains a prerequisite.
- Explicit review before publishing to GitHub; no embedded credentials.
- English templates in PR-01; localization deferred.

## Known issues
PR-02 local runtime checks passed as reported by the user. API assumes trusted local host; worker readiness not checked by API. Failed metadata writes can leave orphaned artifacts; manual recovery ID is returned. PR-03 standalone Vitest results and npm lockfile remain pending. PR-04 public proxy is not a hardened browser isolation boundary; no hostile targets. Basic capture runtime verified by user on the existing Mac Docker setup; repeat-run isolation and capture persistence confirmed by user. Hard-killed jobs can remain active; cancellation, stale reconciliation, full interaction automation, desktop, localization, resume and publishing remain deferred. PR-05 local unit tests and manual Docker GUI checks passed; standalone browser fixture skipped; design sampling is bounded, hover only, inaccessible CSSOM and missing states are explicit limitations. PR-06 does not download source assets or assert licenses; ZIP exports selected run only. PR-06 local tests and manual GUI acceptance passed as reported by user. Example URL is a placeholder.

## Next steps
Complete PR-06 merge on user approval; implement PR-07 Visual Comparison. Record standalone frontend tests and lockfile when available.
