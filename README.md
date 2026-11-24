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

PR-02 adds a local Docker runtime and project registry API; see [Docker setup](docs/DOCKER.md). The independent CLI remains available. React GUI, capture/analysis/comparison/pipeline and the required Tauri macOS app are later stages.

See CONTEXT.md, AGENTS.md and SITE_TRANSFER_SPEC.md.
