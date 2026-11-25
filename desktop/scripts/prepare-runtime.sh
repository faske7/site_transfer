#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# Bundle tracked files from exactly the current commit; never bundle .env or local data.
DEST="$ROOT/desktop/src-tauri/runtime"
mkdir -p "$DEST"
rm -rf "$DEST"
mkdir -p "$DEST"
git archive HEAD compose.yaml Dockerfile .dockerignore pyproject.toml README.md src frontend | tar -x -C "$DEST"
git rev-parse HEAD > "$DEST/RUNTIME_VERSION"
