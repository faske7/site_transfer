# PR-07 Visual Comparison

Select a reference capture and a distinct completed/partial implementation capture, from the same or another project. Capture each authorized public website using the existing workflow. Comparison reuses screenshots, without navigation. Match URL path, viewport name and configured viewport dimensions; no query variants or fuzzy route mapping. Actual PNG dimensions can differ and are reported. No resizing: top-left alignment, white compositing, compare union of real image areas. Pixels differ if any RGB channel differs by more than 16/255; uncovered real area always differs. Pass per pair if actual dimensions match and changed pixels <=1%. Overall pass also requires no unmatched recorded screenshots. This does not establish complete route coverage or functional correctness. Dynamic content is not masked. Structural report compares sampled positional selectors only, if both design reports exist.

Results persist in project volume design/comparisons/<comparison-id>/comparison.json and diff-NNN.png. Red highlights changed pixels; dark background shows reference. Report includes source run IDs and hashes of diffs; input PNG hashes verified. Original captures are read-only. Local synchronous comparison serialized in one API process; max 30 pairs, 16 million pixels per canvas, 120 million total. Larger captures need later batching. No private/localhost implementation capture support: existing browser restrictions remain in effect. Use authorized public staging or compare two runs of same reference. No automatic target deployment or GitHub publishing.

Verify:
- python -m pip install -e '.[dev,server,capture]'
- python -m pytest -v
- docker compose up -d --build --wait
- choose two distinct completed runs of example.com; verify reference/implementation/diff images and actual score
- test a different authorized public implementation with matching route and viewport
- open full JSON, restart Docker and reopen saved report
