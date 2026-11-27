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

The foundation commands validate configuration and scaffold documentation without browser/network calls. The Docker Studio separately supports authorized capture, design sampling, asset inventory, kit export, saved-run comparison and capture-to-kit pipelines.

Every generated project must include root CONTEXT.md and AGENTS.md. Existing files are never intentionally overwritten by init; select a new output directory if documentation already exists.

PR-02 adds a local Docker runtime and project registry API; see [Docker setup](docs/DOCKER.md). The independent CLI remains available. PR-03 adds the React Studio GUI at http://localhost:8080/ when built with Docker. The Tauri desktop controller reuses this GUI. See [GUI setup](docs/GUI.md).

See CONTEXT.md, AGENTS.md and SITE_TRANSFER_SPEC.md.

PR-04 adds authorized reference capture, per-run screenshots and a Studio gallery. See [capture setup and limitations](docs/CAPTURE.md).

PR-05 adds sampled design intelligence to new reference captures. See [design evidence and limits](docs/DESIGN.md).

PR-06 adds bounded asset inventory and portable Codex Reference Kit export. See [reference kit](docs/REFERENCE_KIT.md).

PR-07 adds saved-run visual comparison, pixel diffs and sampled structural reports. See [comparison](docs/COMPARISON.md).

PR-08 adds capture-to-kit pipeline and reviewed host GitHub publication. See [pipeline](docs/PIPELINE.md).

PR-09 adds native macOS Tauri controller and bundled Docker runtime. See [desktop build and migration](docs/DESKTOP.md).

## MVP acceptance — 2026-11-25

All nine initial stages accepted by the user; PR-09 desktop acceptance recorded for merge. See [technical report](docs/TECHNICAL_REPORT.md) and [proposed development roadmap](docs/ROADMAP.md). This is a personal-use MVP, not a hardened public release.

PR-10 adds durable lifecycle recovery and worker readiness. See [upgrade and recovery](docs/RECOVERY.md); stop old API and worker before upgrading, and rebuild the desktop bundle.

PR-11 full Backup & Restore deferred by user. PR-12 adds a security/build baseline; see [hardening and acceptance](docs/HARDENING.md). Full backup/restore remains a release gate.

PR-13 adds opt-in isolated hover/focus/click/scroll state evidence, separate viewport screenshots, gallery and Reference Kit export. See [interaction capture](docs/INTERACTIONS.md).

PR-14 Advanced Design Intelligence adds design report v2, normalized sampled CSS, semantic metadata and bounded responsive width probes. See [design evidence](docs/DESIGN.md).

PR-15 adds opt-in [scroll timeline evidence](docs/SCROLL_TIMELINE.md) for scroll-driven pages and lazy-loaded mobile layouts, with hashed ordered viewport frames and difference maps in the Reference Kit.

PR-16 introduces [Scroll Intelligence](docs/SCROLL_INTELLIGENCE.md), shared wheel input and sampled root/nested/horizontal/transform observations for scroll states and timelines.

PR-17 adds bounded shared DOM candidate caching, pixel-equivalent timeline diff optimization and additive diagnostics. See [architecture](docs/SCROLL_PERFORMANCE.md) and [benchmark/acceptance](docs/SCROLL_PERFORMANCE_BENCHMARK.md).
