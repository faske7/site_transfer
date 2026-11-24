# Project context — Site Transfer Studio

## Purpose
Build a local-first website reference analysis platform that hands an implementation-ready evidence package to Codex, reducing repeated browser work and token usage. Deliver CLI, Web GUI and a mandatory macOS desktop application.

## Architecture
src/site_transfer remains independent of the API and UI. PR-01 implements config, documentation, validation and CLI. Future API/worker call shared core services; Docker Compose manages FastAPI, PostgreSQL, Redis and Celery. React UI is shared with a Tauri desktop shell. See SITE_TRANSFER_SPEC.md for the approved nine-stage roadmap.

## Technology stack
Implemented: Python 3.11+, setuptools, JSON Schema Draft 2020-12, Jinja2, pytest.
Planned: FastAPI, PostgreSQL, Redis, Celery, React/TypeScript/Vite, Playwright Chromium, Tauri 2/Rust, Docker Compose with native arm64 support.

## Important files
- pyproject.toml: dependencies and CLI entry point.
- schemas/transfer.schema.json: public config schema.
- templates/: public documentation templates.
- src/site_transfer/resources/: packaged mirrors; tests enforce parity.
- examples/remaxdelux.json: synthetic sample configuration.
- SITE_TRANSFER_SPEC.md: approved architecture and PR sequence.

## Development commands
- python -m pip install -e '.[dev]'
- python -m pytest
- site-transfer validate examples/remaxdelux.json
- site-transfer plan examples/remaxdelux.json
Docker and UI commands are not available in PR-01.

## Current status
PR-01 foundation is a draft awaiting runtime tests and review. Roadmap revised to Docker/Web GUI and mandatory Tauri app. No API, containers, browser capture or desktop app in PR-01.

## Technical decisions
- Root CONTEXT.md is mandatory for this repository and every generated project.
- Capture reference evidence upstream and provide it to Codex.
- Keep CLI independent; API and UI must not duplicate core logic.
- Local-first loopback runtime; no Docker socket in server containers.
- Tauri manages Docker lifecycle on the host; Docker remains a prerequisite.
- Explicit review before publishing to GitHub; no embedded credentials.
- English templates in PR-01; localization deferred.

## Known issues
Runtime tests not verified. Browser pipeline, API, GUI, desktop, localization, resume and publishing are not implemented in PR-01. Example URL is a placeholder.

## Next steps
Review/test PR-01. PR-02 Docker + Backend API. PR-03 Web GUI. Follow the nine-stage roadmap through mandatory PR-09 macOS app.
