#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || { echo "Build on native Apple Silicon macOS"; exit 1; }
command -v cargo >/dev/null
xcode-select -p >/dev/null
[[ -f package-lock.json && -f src-tauri/Cargo.lock ]] || { echo "Desktop lockfiles required; see docs/HARDENING.md"; exit 1; }
npm ci --no-audit --no-fund
cargo metadata --locked --manifest-path src-tauri/Cargo.toml --format-version 1 >/dev/null
bash scripts/prepare-runtime.sh
# Generate a deterministic app icon without external image assets.
python3 scripts/icon.py
npm run tauri -- icon src-tauri/icons/source.png
npm run tauri -- build --target aarch64-apple-darwin --bundles app,dmg -- --locked
