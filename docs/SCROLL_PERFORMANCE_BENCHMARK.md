# PR-17 benchmark and acceptance

Baseline: d2c438be784da32dea9764c5c68898be4e6dc08e (PR-16). Compare against the exact PR-17 commit under test. Direct checkout in the remote editing environment failed with DNS resolution of github.com. Chromium 144.0.7559.96, Pillow 12.3.0 and Playwright 1.57.0 were available there, but project pins Playwright 1.56.0. Previous preliminary figures are not independently reproduced against this final candidate; do not use them as release evidence.

## Reproduce locally
From a clean PR-17 checkout on the same machine:

```sh
python -m pip install -e '.[dev,server,capture]'
python -m playwright install chromium
git worktree add --detach ../site-transfer-pr16-baseline d2c438be784da32dea9764c5c68898be4e6dc08e
python -m pytest tests/test_scroll_performance.py tests/test_scroll_intelligence.py tests/test_scroll_timeline.py tests/test_interaction_capture.py tests/test_cookie_consent.py tests/test_capture_quality.py -v
python -m pytest -ra
python scripts/benchmark_scroll_performance.py --baseline ../site-transfer-pr16-baseline --runs 7 > /tmp/pr17-benchmark.json
```

The opt-in component benchmark loads the actual legacy JS and diff implementation from the pinned baseline, alternates runs in a single browser, checks exact snapshot equality and decoded overlay equality, and uses identical raw screenshots for both pixel pipelines. It reports median/p95 wall and Python CPU times, candidate counters and hashes for desktop/mobile. It excludes screenshot generation from timed pixel processing and page setup from timed observations. DOM fixture scroll inputs use deterministic scrollTo, not production wheel/settle; this is not a full capture benchmark.

## Results
| Metric | Before | After |
|---|---|---|
| DOM scans / geometry / styles | pending | pending |
| DOM / pixel median and p95 | pending | pending |
| Python CPU time | pending | pending |
| Python and Chromium peak RSS | pending | pending |
| Full capture processing and elapsed | pending | pending |
| Frame and decoded overlay equivalence | pending final checkout | pending final checkout |

For full acceptance, run identical maximum-coverage reference configs on both commits in fresh processes with identical browser version, hardware, worker settings, settle intervals, screenshot budgets and context settings. Record raw frame hashes, resolution, decoded overlays, manifest/ZIP validation, stop reasons, wall time, wait time, process CPU and worker/browser peak RSS. Repeat after warm-up; report median/p95 and repeat long sequences to test retained memory. Compare deterministic fixture frames exactly; live-site animation variability is not proof of regression or equivalence. Run frontend tests/build if consumers change; no frontend source changes in this candidate. No wall-clock unit-test gates. Do not merge until actual acceptance evidence is recorded.
