# PR-08 Pipeline & GitHub

Run pipeline from project capture panel after authorization. Existing capture pass includes design and assets, then worker creates a durable ZIP checkpoint. Existing captures can build/retry a kit without browser navigation. ZIP I/O retries at most twice per build; validation errors are not retried. Cancellation is cooperative between viewport attempts; queued jobs are marked failed with a cancellation reason and running jobs preserve completed evidence. No force-kill. Capture retries require a fresh run. Hard-killed running/building records and broker-loss queued records still require manual recovery; no automatic stale reconciliation or per-page resume. Kit generation during capture shares its task time limit. Existing comparison remains optional and separate.

Host publication only: install gh, authenticate with gh auth login, download the pipeline kit, inspect all files and rights, then use:

```sh
shasum -a 256 /path/to/reference-kit.zip
site-transfer publish /path/to/reference-kit.zip --repo OWNER/PRIVATE_REPO --sha256 REVIEWED_HASH --approve
```

Only active private existing repositories, max 20 MiB ZIP. Publishes ZIP on a unique new branch and opens a draft PR; does not merge or modify main. No GitHub credentials in Docker, project JSON or browser. On ambiguous failure inspect the reported branch before retrying; no automatic remote rollback. ZIP must be extracted locally for Codex; no individual file publishing yet. No live GitHub publication test in automated suite. Review all evidence before sharing.

Test with python -m pip install -e '.[dev,server,capture]' and python -m pytest -v. Rebuild Compose; verify pipeline kit ready/download/hash, existing capture build, queued/running cancellation, persistence. For live publication use a disposable private repository with an initial commit and verify draft PR.
