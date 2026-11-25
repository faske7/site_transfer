# PR-09 macOS desktop (Apple Silicon)

The app has a bundled local controller and a separate embedded Studio window served by the same Docker React frontend. The remote loopback window has no native command capability; new windows are denied. Open in browser remains available for report tabs/downloads. Docker Desktop with local desktop-linux ARM64 context is mandatory. No Docker socket mounted, no arbitrary shell or Docker arguments, no automatic GitHub publication.

## Build on Mac

Install Xcode Command Line Tools, Rust (rustup, aarch64-apple-darwin), Node 22+ and Python 3. From the committed PR branch:

```sh
cd desktop
npm install
bash scripts/prepare-runtime.sh
python3 scripts/icon.py
npm run tauri -- icon src-tauri/icons/source.png
cargo test --manifest-path src-tauri/Cargo.toml
npm run build
```

Artifacts expected in desktop/src-tauri/target/aarch64-apple-darwin/release/bundle/app/Site Transfer.app and bundle/dmg/*.dmg. Copy app to Applications or install from DMG. Actual compilation and packaging must be verified on macOS. Personal unsigned build only; distribution signing/notarization is separate. Generated runtime resources are tracked-source snapshots from HEAD, not local working-tree edits.

## Existing runtime migration

Do not delete volumes or change existing PostgreSQL password. Close active jobs first. In controller click Open data folder, copy the original repository .env there and chmod 600. The app identifier is tech.sitetransfer.studio. Only POSTGRES_PASSWORD and optional plain numeric SITE_TRANSFER_PORT are allowed (comments and blanks accepted). Do not copy tokens. Same Compose project name site-transfer and same named volumes; use same Docker Desktop context. The new app rebuilds the runtime from its bundled source. No database reset or volume removal. Fresh install can use Initialize new runtime only when existing named volumes are absent.

## Acceptance

- Docker stopped: actionable status and no start action until engine is ready.
- Start services, check status; API ready is not worker readiness. Inspect worker running.
- Open Studio and verify previous projects, screenshots, comparisons and pipeline kits.
- Export a completed capture using project/run UUIDs to the app data exports folder; opens Finder. Docker volume is not a native project directory; ZIP is not automatically extracted.
- Stop after confirmation, start again; verify persistence. Closing app leaves services running. No down -v.
- Occupied port: startup must fail instead of silently changing port; inspect compose logs on host.
- Install updated bundle, verify data and volumes preserved. Removing app does not remove Docker data.
- Run a fresh install separately only after backing up existing data; do not delete volumes to test.

Limitations: no automatic Docker Desktop installation/start, no remote daemon, no arbitrary path import UI, no auto-update or notarization, no guaranteed full embedded downloads/new tabs. Native build, tests and real launch pending. npm and Cargo lockfiles need to be committed after local verification. Synchronous host subprocesses run in blocking worker with time limits; a timeout can leave Compose operations in progress. No cross-process desktop singleton or hardened browser isolation. Review runtime state before retrying.
