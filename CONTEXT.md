# Project context — Site Transfer

## Purpose
Build a JSON-driven Python CLI to collect reference-site evidence once and hand an implementation-ready package to Codex, reducing repeated browser work and token usage.

## Architecture
src/site_transfer is the CLI package. PR-01 implements config, documentation, validation and CLI. Later modules are described in SITE_TRANSFER_SPEC.md.

## Technology stack
Python 3.11+, setuptools, JSON Schema Draft 2020-12, Jinja2, pytest. Playwright/Chromium planned for PR-02.

## Important files
- pyproject.toml: dependencies and CLI entry point.
- schemas/transfer.schema.json: public config schema.
- templates/: public documentation templates.
- src/site_transfer/resources/: packaged mirrors of schema/templates; tests enforce parity.
- examples/remaxdelux.json: synthetic sample configuration.
- SITE_TRANSFER_SPEC.md: roadmap and architecture.

## Development commands
- python -m pip install -e '.[dev]'
- python -m pytest
- site-transfer validate examples/remaxdelux.json
- site-transfer plan examples/remaxdelux.json

## Current status
PR-01 foundation implementation; runtime test status must be checked before merge. No live capture, comparison or GitHub publication implemented in the CLI.

## Technical decisions
- Root CONTEXT.md is mandatory for this repository and every generated project.
- Reference screenshots should be collected upstream, organized and supplied to Codex rather than recaptured by it.
- Use explicit configuration; GitHub authentication will use gh CLI, not embedded tokens.
- Review is required before future publishing.
- Documentation is rendered in English in PR-01; localization is deferred.

## Known issues
Browser pipeline, localization, resume and GitHub publishing are not implemented. The example source URL is a placeholder. No local previous-session changes are available in this repository baseline.

## Next steps
Run foundation tests and review PR-01. Implement Browser & Screenshot Capture in PR-02.
