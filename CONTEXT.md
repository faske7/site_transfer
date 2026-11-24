# Project context — Site Transfer Studio

## Purpose
Build a local-first website reference analysis platform that hands an implementation-ready evidence package to Codex, reducing repeated browser work and token usage. Deliver CLI, Web GUI and a mandatory macOS desktop application.

## Architecture
src/site_transfer remains independent of the API and UI. PR-01 implements config, documentation, validation and CLI. PR-02 adds optional server adapters under src/site_transfer/server; Docker Compose manages FastAPI, PostgreSQL, Redis and Celery. React UI is shared with a Tauri desktop shell. See SITE_TRANSFER_SPEC.md for the approved nine-stage roadmap.

## Technology stack
Implemented: Python 3.11+, setuptools, JSON Schema Draft 2020-12, Jinja2, pytest.
PR-02 implementation: FastAPI, PostgreSQL 17, Redis 7, Celery and Docker Compose. Planned: React/TypeScript/Vite, Playwright Chromium, Tauri 2/Rust. Native arm64 runtime needs verification.

## Important files
- pyproject.toml: dependencies and CLI entry point.
- schemas/transfer.schema.json: public config schema.
- templates/: public documentation templates.
- src/site_transfer/resources/: packaged mirrors; tests enforce parity.
- examples/remaxdelux.json: synthetic sample configuration.
- SITE_TRANSFER_SPEC.md: approved architecture and PR sequence.
- compose.yaml, Dockerfile, docs/DOCKER.md: local runtime.
- src/site_transfer/server/: API, registry, migration and worker.

## Development commands
- python -m pip install -e '.[dev]'
- python -m pytest
- site-transfer validate examples/remaxdelux.json
- site-transfer plan examples/remaxdelux.json
- python -m pip install -e '.[dev,server]'
- docker compose config --quiet
- docker compose up -d --build
- curl -fsS http://localhost:8080/health/ready
React GUI is not yet available.

## Current status
PR-02 is a stacked draft based on unmerged PR-01. Docker/API implementation added; runtime and Apple Silicon smoke tests have not run. Create/list/read project registry generates mandatory documents before saving metadata. Worker runtime has no capture tasks yet.

## Technical decisions
- Root CONTEXT.md is mandatory for this repository and every generated project.
- Capture reference evidence upstream and provide it to Codex.
- Keep CLI independent; API and UI must not duplicate core logic.
- Local-first loopback runtime; no Docker socket in server containers.
- Tauri manages Docker lifecycle on the host; Docker remains a prerequisite.
- Explicit review before publishing to GitHub; no embedded credentials.
- English templates in PR-01; localization deferred.

## Known issues
Runtime tests not verified. API assumes trusted local host; worker readiness not checked by API. Failed metadata writes can leave orphaned artifacts; manual recovery ID is returned. GUI, capture, export, automated reconciliation, desktop, localization, resume and publishing remain deferred. Example URL is a placeholder.

## Next steps
Review and test PR-01 then PR-02; verify Docker on Apple Silicon. Retarget PR-02 to main after PR-01 merge if needed. PR-03 Web GUI follows.
