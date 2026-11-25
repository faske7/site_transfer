# PR-12 — Security and build baseline

PR-11 Backup & Restore is explicitly deferred by the user. Do not interpret a Reference Kit as a full backup. No database migration or volume deletion is part of PR-12.

## Scope and decisions
- Docker frontend installs from existing committed npm lockfile using npm ci.
- Native build requires desktop package-lock.json and Cargo.lock; do not invent them. Generate on the actual Apple Silicon machine, review and commit them to the PR. Cargo metadata/build uses --locked. Python and base image digests are not fully pinned; bit-for-bit reproducibility is not claimed.
- Runtime bundle checks tracked input modes and obvious secret filenames, refuses symlinks/submodules, and archives HEAD only. Docker ignores common secret files and native build outputs. This is not content-based secret scanning. Keep secrets out of tracked files.
- Proxy rejects ambiguous URLs, explicit port zero, scoped addresses, IPv6 transition/special ranges, mixed public/private DNS results and hop-by-hop request headers. HTTP resolves once and connects to the checked numeric address. HTTPS CONNECT still permits only public addresses on 443.
- The browser route policy does NOT guarantee pre-request blocking of every HTTPS cross-origin redirect hop; CONNECT cannot inspect encrypted requests. Chromium remains in the worker network namespace. This is not hardened hostile-site isolation or authenticated remote deployment. Use authorized trusted references only.
- Browser cross-origin access to local API/health is rejected by Fetch Metadata and Origin where present; no-store, frame denial, nosniff, no-referrer and same-origin resource policy are added. Native clients without these browser headers remain trusted local clients.
- Tauri controller navigation is restricted to bundled origin/index and new windows denied. Studio window is restricted to exact HTTP loopback origin and has no native capability. Rust unit tests check predicates, not actual IPC enforcement in running WebKit.

## Local acceptance (Apple Silicon)

From committed branch; do not run an older desktop bundle against the new runtime.

```sh
source .venv/bin/activate
python -m pip install -e '.[dev,server,capture]'
python -m playwright install chromium
python -m pytest -v
cd frontend
npm ci
npm run test
npm run build
cd ..
cd desktop
# If absent, generate real lockfiles on this host:
test -f package-lock.json || npm install --package-lock-only
test -f src-tauri/Cargo.lock || cargo generate-lockfile --manifest-path src-tauri/Cargo.toml
npm ci
bash scripts/prepare-runtime.sh
python3 scripts/icon.py
npm run tauri -- icon src-tauri/icons/source.png
cargo test --locked --manifest-path src-tauri/Cargo.toml
npm run build
find src-tauri/target/aarch64-apple-darwin/release/bundle/dmg -name '*.dmg' -exec shasum -a 256 {} \;
cd ..
git status --short
```

Review and commit desktop lockfiles after generation; do not commit generated runtime, target, or icons. Run the PostgreSQL integration suite per RECOVERY.md with the disposable database. For Docker upgrade close old desktop app, finish jobs and use docker compose stop api worker, then docker compose up -d --build --wait; verify schema 4, ready, previous captures, new pipeline and ZIP export. Rebuild desktop from the accepted commit. Do not run down -v.

## Separate manual checks
- From controller, verify only local app commands work; attempt navigating controller off-origin and new windows, and verify Studio cannot invoke native commands. Do not test destructive actions on existing data.
- Check Docker unavailable and occupied-port startup on a disposable environment; verify clear failure without starting a foreign service.
- Clean install, upgrade, restart and uninstall behavior: use isolated test volumes and a separate test host where needed. Do not delete existing volumes to test uninstall. Verify retained project hashes.
- Verify actual app binary is arm64 and DMG checksum. Not signing/notarizing in this PR.

Status: tests, lockfile generation, actual build and manual checks pending. No CI run or independent Mac verification claimed. Full backup/restore, strict egress isolation, dependency audit and signing remain release blockers for public distribution.
