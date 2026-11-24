# Site Transfer Studio

Token-efficient, evidence-first website recreation workflow for AI coding agents.

## Quick start

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
site-transfer validate examples/remaxdelux.json
site-transfer plan examples/remaxdelux.json
site-transfer init examples/remaxdelux.json --output ./output/demo
site-transfer validate-project ./output/demo
python -m pytest
```

The example uses a placeholder URL; replace it with an authorized reference before capture.

PR-01 supports configuration validation, planning and documentation scaffolding. Capture, measurements, asset analysis, visual verification, publication and end-to-end execution are future stages. No browser or network calls are made by these commands.

Every generated project must include root CONTEXT.md and AGENTS.md. Existing files are never intentionally overwritten by init; select a new output directory if documentation already exists.

The approved roadmap adds Docker Compose + FastAPI, React web GUI, capture/analysis/comparison/pipeline, and a required Tauri macOS app (Docker remains a prerequisite). The CLI stays independent. None of those later stages are implemented in PR-01.

See CONTEXT.md, AGENTS.md and SITE_TRANSFER_SPEC.md.
