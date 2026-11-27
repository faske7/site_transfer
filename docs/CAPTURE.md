# PR-04 reference capture

Rebuild the existing Compose project (preserve .env and volumes):

```sh
docker compose up -d --build --wait
docker compose ps -a
docker compose exec worker python -c 'from playwright.sync_api import sync_playwright; print("Playwright import OK")'
open http://localhost:8080
```

Open the existing example.com project, confirm authorization, start capture. Expect one desktop and one mobile PNG on completion. Inspect job status, repeat capture, verify distinct run IDs and history after restart. Run Python tests with `python -m pip install -e '.[dev,server]'` and `python -m pytest -v`. Run frontend tests/build as documented in GUI.md.

Evidence: `/data/projects/<project-id>/design/reference/runs/<job-id>/` contains routes.json, capture-manifest.json, screenshots/<viewport>/*.png. PostgreSQL stores progress and errors. The target CONTEXT.md receives a run summary. Screenshot responses are scoped to recorded project/job/artifact indexes.

Scope: authorized public HTTP(S), default ports, same-origin route discovery, up to 30 pages and four viewports (max 2560 × 2160), 90-minute job timeout. Query variants/fragments stripped. Full-page screenshots exceeding safety dimensions fail explicitly. Browser is headless. Public CDN resources may load; nonpublic destinations are denied by the local proxy, which connects to DNS-checked public IPs. Browser routing is best effort (redirects can contact external public hosts before final origin validation). This is not hardened isolation against malicious pages: browser and worker share a container; Chromium sandbox is not enabled by Playwright default. Do not use hostile targets or expose remotely. Full egress isolation and DNS/redirect adversarial integration tests are still needed. Interaction states, measurements, lazy-load scrolling, robots policy automation, cancellation, checkpoint recovery, stale-job reconciliation and export are later work. A hard kill or broker loss may leave an active record; do not claim it completed. No automatic recovery in PR-04.

Existing projects/volumes are preserved. PR-04 migration is additive. Native ARM64 browser launch and actual capture need local verification.
