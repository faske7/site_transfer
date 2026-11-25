# Project context — Site Transfer Studio

## Purpose
Build a local-first website reference analysis platform that hands an implementation-ready evidence package to Codex, reducing repeated browser work and token usage. Deliver CLI, Web GUI and a mandatory macOS desktop application.

## Architecture
src/site_transfer remains independent of the API and UI. PR-01 implements config, documentation, validation and CLI. PR-02 adds optional server adapters under src/site_transfer/server; Docker Compose manages FastAPI, PostgreSQL, Redis and Celery. PR-03 adds React UI under frontend/; FastAPI serves the built static files at the same origin. PR-09 adds a local Tauri controller and a separate loopback Studio webview without native capabilities. See SITE_TRANSFER_SPEC.md for the approved nine-stage roadmap.

## Technology stack
Implemented: Python 3.11+, setuptools, JSON Schema Draft 2020-12, Jinja2, pytest.
PR-02 implementation: FastAPI, PostgreSQL 17, Redis 7, Celery and Docker Compose. PR-03 implementation: React 19, TypeScript, Vite, Vitest, Node 22 build stage. PR-04 adds Playwright Chromium 1.56.0. PR-09 adds Tauri 2/Rust (local Apple Silicon build and launch confirmed by user). PR-02 native arm64 runtime was verified by user.

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
- comparison.py, server/comparisons.py: saved-run comparison and persistence.
- docs/COMPARISON.md: thresholds and limitations.
- pipeline.py, github.py, docs/PIPELINE.md: checkpointed kit build and host publication.
- desktop/: Tauri controller and build scripts; docs/DESKTOP.md.
- docs/TECHNICAL_REPORT.md: MVP acceptance snapshot and architecture.
- docs/ROADMAP.md: proposed post-MVP work and release gates.
- server/lifecycle_schema.py, server/recovery.py, docs/RECOVERY.md: PR-10 lifecycle recovery.
- docs/HARDENING.md: PR-12 security and build checks.
- interaction_capture.py, docs/INTERACTIONS.md: PR-13 declared state evidence.

## Development commands
- python -m pip install -e '.[dev]'
- python -m pytest
- site-transfer validate examples/remaxdelux.json
- site-transfer plan examples/remaxdelux.json
- python -m pip install -e '.[dev,server]'
- docker compose config --quiet
- docker compose up -d --build
- curl -fsS http://localhost:8080/health/ready
- cd frontend && npm ci && npm run test && npm run build
- open http://localhost:8080 (Docker GUI; use configured port)

## Current status
PR-01 merged into main (25d2b459); user verified all 14 foundation tests on macOS, Python 3.13.7, pytest 9.2.0 (0.70 s). PR-02 integration PR #3 merged into main (fb1afbcd). User verified 20/20 Python tests (5.25 s; one Starlette TestClient deprecation warning), native linux/aarch64 Docker, all five services, API create/list, generated documents, Celery ping and persistence after restart. The last three checks were confirmed by the user without raw logs. Create/list/read project registry generates mandatory documents before saving metadata. PR-04 adds Celery capture tasks with PostgreSQL job state and per-run artifacts. PR-03 Docker build and GUI launch succeeded according to the user; all six manual GUI acceptance checks passed (existing project, creation, validation, import, details, readiness). Standalone Vitest results and npm lockfile are not supplied. PR-03 merged into main (b11b7592) on user approval. PR-04: user confirmed local tests passed and an actual capture completed with two desktop/mobile screenshots. Exact test counts and raw logs were not supplied. User confirmed repeat-run isolation, gallery history and persistence after restart; PR #5 merged into main (d384499). PR-05 adds design evidence during the same capture pass. Local macOS Python 3.13.7 / pytest 9.2.0: 36 passed, 1 skipped (Chromium not installed locally), 1 Starlette warning, 5.19 s. User confirmed all six GUI checks: completed capture, desktop/mobile screenshots, two design reports, tokens JSON opens with typography/colors/spacing/responsive, prior history preserved. Standalone browser fixture not verified. PR-05 merged into main (4031690) on user approval. PR-06 adds inventory-only assets and portable selected-run ZIP export. User supplied local test output: 45 passed, 1 skipped (local Chromium unavailable), no failures shown. All nine new tests passed. User confirmed six manual GUI acceptance checks (completed capture, inventory, ZIP download, mandatory documents, screenshot/JSON evidence, prior-run export). PR #7 merged into main (43250b8). PR-07 adds saved-run visual comparison. User supplied test output: 53 passed, 1 skipped (local Chromium unavailable), no failures shown; all eight new comparison tests passed. User confirmed six manual GUI checks: run selection, comparison execution, three images, similarity, JSON and persistence after restart. PR #8 merged into main (89b4f2d). PR-08 implements capture-to-kit pipeline checkpoints, cooperative cancellation, bounded kit retry and host-only reviewed GitHub ZIP draft publication. Local macOS tests: 59 passed, 1 skipped (local Chromium unavailable), 1 Starlette warning, 1.77 s. User confirmed seven manual pipeline checks: capture completed, kit ready, SHA256, download, retry from saved capture, cancellation and persistence. GitHub publication was mocked only; no live publication verified. PR #9 merged into main (797dd88). PR-09 implements native controller, versioned runtime bundle, local Docker commands and Finder ZIP export; macOS arm64 local Rust tests: 6 passed, 0 failed; Rust/Cargo 1.100.0, Node 24.18.0, npm 11.16.0, Docker 29.9.3, Compose 5.7.1. User confirmed all ten desktop acceptance checks on 2026-11-25: app launch, existing PostgreSQL configuration, start services, Studio opening, existing projects/captures, new capture, Finder kit export, stop/start persistence, relaunch persistence and DMG build/check. Raw release build log, DMG checksum and separate edge-case logs were not supplied. PR #10 merged into main (005a52a). Latest Python regression evidence is PR-08 (59 passed, 1 skipped, 1 warning); not rerun for PR-09.

## Technical decisions
- Root CONTEXT.md is mandatory for this repository and every generated project.
- Capture reference evidence upstream and provide it to Codex.
- Keep CLI independent; API and UI must not duplicate core logic.
- Local-first loopback runtime; no Docker socket in server containers.
- Tauri manages Docker lifecycle on the host; Docker remains a prerequisite.
- Explicit review before publishing to GitHub; no embedded credentials.
- English templates in PR-01; localization deferred.

## Known issues
PR-02 local runtime checks passed as reported by the user. API assumes trusted local host; worker readiness added in PR-10. Failed metadata writes can leave orphaned artifacts; manual recovery ID is returned. PR-12 verified standalone Vitest 5/5 and committed frontend/package-lock.json, desktop/package-lock.json and desktop/src-tauri/Cargo.lock (verified at 7033b5b). PR-04 public proxy is not a hardened browser isolation boundary; no hostile targets. Basic capture runtime verified by user on the existing Mac Docker setup; repeat-run isolation and capture persistence confirmed by user. PR-10 adds schema 4, bounded durable dispatch and stale recovery, owner-token fencing, new-run capture retry, isolated kit attempts, transactional events and worker heartbeat readiness; local macOS Python 3.13.7 / pytest 9.2.0: 64 passed, 12 skipped, 1 warning (2.19 s); with isolated PostgreSQL 17, 75 passed, 1 skipped (Chromium absent), 1 Starlette warning (4.95 s). All 16 new tests passed, including 11 real PostgreSQL integration tests. User confirmed nine manual checks: migration to schema 4, all readiness checks, old evidence, new pipeline, lifecycle JSON, cancellation, new UUID retry, worker readiness loss and recovery. Actual Celery hard-kill/broker outage fault injection not separately demonstrated; tests simulate lease expiration and failed delivery. PR #11 merged into main (ab655e8). Per-page resume, full interaction automation and localization remain deferred. PR-05 local unit tests and manual Docker GUI checks passed; standalone browser fixture skipped; design sampling is bounded, hover only, inaccessible CSSOM and missing states are explicit limitations. PR-06 does not download source assets or assert licenses; ZIP exports selected run only. PR-06 local tests and manual GUI acceptance passed as reported by user. PR-07 unit tests and manual GUI checks passed as reported by user; comparison is bounded synchronous pixel analysis, sampled positional selectors only; no localhost target capture or dynamic masking. PR-08 local tests and manual pipeline checks passed as reported by user; no hard-kill recovery or automatic remote rollback, publication private repo and ZIP only. PR-09 Rust tests and ten desktop checks passed as reported by user; Docker-unavailable, occupied-port, clean-install, upgrade/uninstall and capability-boundary checks are not independently evidenced. Existing .env must be imported; no new password over existing volumes. Native project folders contain exports, not raw Docker volume contents. Signing/notarization pending; PR-12 locks committed. Example URL is a placeholder.

## Next steps
Initial nine-stage MVP accepted and merged with documented scope gaps. PR-10 acceptance complete; rebuild desktop bundle after upgrade (not yet confirmed). PR-11 Backup & Restore explicitly deferred by user; no implementation or merge. PR-12 security/build baseline adds locked frontend install, bundle input checks, proxy/address hardening, local API cross-origin read protection and Tauri navigation guards. PR-12 local macOS Python 3.13.7: 83 passed, 11 skipped (isolated PostgreSQL DSN absent), 1 Starlette warning, 12.48 s; all 18 new Python tests and actual Chromium fixture passed. Rust 1.100.0: 8/8 passed including 2 negative origin predicate tests. Frontend upgraded Vite 7.2.2 -> 7.3.8 and Vitest 3.2.4 -> 5.1.2; React unchanged; user supplied npm audit and npm audit --omit=dev both zero vulnerabilities, npm ci, 5/5 Vitest and production build passed. Desktop npm audit zero; desktop lockfiles committed and verified on GitHub. User confirmed native release build and eight manual checks: launch, Start services, Open Studio, existing projects, new capture, pipeline kit, download, restart persistence. PR #12 merged into main (a402164). Actual DMG SHA256, repeated PostgreSQL regression, live WebKit IPC denial, occupied port, unavailable Docker and clean install/uninstall remain unverified. npm allow-scripts warnings and Python Starlette deprecation remain. Full egress isolation, Python/base image pinning, dependency audits beyond npm, signing and deferred full backup/restore remain release gaps. PR-13 adds explicit bounded per-route/per-viewport state scenarios in the config schema, fresh offline-after-load contexts, hashed state screenshots and report, API/gallery and selected-run kit inclusion. Tests and manual acceptance pending; no DB migration. Real process-kill/broker outage exercise remains pending. Follow docs/TECHNICAL_REPORT.md and docs/ROADMAP.md for stabilization and v1.0 gates. Prioritize recoverable jobs, backup/restore, reproducible builds, actual browser and cross-project fixtures; then interaction coverage and Codex evidence efficiency. Live GitHub publication remains unverified.
