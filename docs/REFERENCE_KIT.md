# PR-06 Assets & Reference Kit

New captures inventory observed images, icons, SVG presence, media, stylesheets, font-face metadata and sampled CSS backgrounds from the existing browser visit. No additional asset fetches or source asset bytes. URLs omit query/fragment/credentials; inline payloads are not copied. License remains unknown, redistribution not authorized, asset byte hash null. Inventory is bounded, deduplicated by kind/source/detail, and not exhaustive (up to 500 observations per viewport pass). Older runs remain available.

From a terminal completed/partial capture with screenshots, Download Reference Kit creates a ZIP on demand. It includes fresh mandatory root CONTEXT.md, AGENTS.md, TASK.md and README.md, selected run evidence under design/reference/, and reference-kit.json with byte sizes and SHA256 of included evidence. Screenshot hashes are checked against the registry. Missing/tampered evidence rejects export. Files are allowlisted, no symlinks/traversal, 512 MiB input cap. Temporary ZIP removed after response; interrupted process can leave a temporary file. No automatic GitHub push or target application generation. Review screenshots and reports for confidential material and rights before sharing; URL path strings and screenshots may contain sensitive content.

Verification:
- python -m pytest -v
- docker compose up -d --build --wait
- Run new authorized capture; open Assets inventory, inspect unknown licenses and no downloaded bytes.
- Download ZIP; unzip into empty folder; run site-transfer validate-project on that folder.
- Inspect TASK.md and reference-kit.json; verify old run export and selected-run isolation.
- Confirm original capture history is unchanged.

Homepage desktop timeline sequences may include horizontal-panorama.png and horizontal-storyboard.png, each with source frame provenance and SHA256. The storyboard is a discrete overview, not a continuous page; use original frames for animation. See [Horizontal Homepage Capture](HORIZONTAL_HOMEPAGE_CAPTURE.md).
