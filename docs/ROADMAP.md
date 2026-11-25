# Site Transfer Studio — proposed post-MVP roadmap

Дата: 2026-11-25. Предлагаемый порядок, не утверждённые сроки или обязательства. Каждый этап — отдельный PR с тестами, CONTEXT.md и явной приёмкой. Номера ниже — логические этапы, не GitHub PR IDs.

## Phase A — stability / v0.9.x (P0)
| Stage | Work | Acceptance |
|---|---|---|
| PR-10 | Job lifecycle: durable attempt/lease, heartbeat, bounded stale recovery, cancel/retry fencing, durable stage events, worker readiness | Simulate killed worker, lost dispatch, duplicate delivery and cancel race; no stuck active jobs; preserve evidence; idempotent checkpoint retry |
| PR-11 (deferred by user) | Backup/restore: database + evidence manifest, consistent export/import, schema compatibility, restore dry-run, safe desktop diagnostics | Restore into isolated volumes; compare projects, run IDs and artifact hashes; no overwrite of existing data |
| PR-12 | Reproducible builds and security baseline: npm/Cargo locks, browser fixture, Docker integration, Rust capability negative tests, port collision, unavailable Docker, clean install, upgrade/uninstall; redirect and egress review | All gates on ARM64, actual tests not mocked where integration needed, app/dmg hashes, no secrets in bundles |

## Phase B — evidence quality / v0.10 (P1)
| Stage | Work | Acceptance |
|---|---|---|
| PR-13 | Interaction coverage: explicitly configured safe hover/focus/click/menu/modal/accordion/scroll; state IDs and screenshots; no destructive actions or form submissions | Fixture captures all declared states on desktop/mobile, records skipped/unsafe actions; bounded execution |
| PR-14 | Design intelligence: responsive breakpoint probes, normalized layout/type/motion tokens, real design-report schema alignment, accessibility metadata, declared vs observed distinction | Fixture expected values match actual JSON; report gaps; compare real cross-project records |
| PR-15 | Reference Kit v2: route/state matrix, coverage summary, compact indexed task, evidence digests, allowed asset import with explicit rights, selected incremental evidence | Codex uses existing screenshots; no duplicates; missing evidence explicit; verify kit integrity and required docs |

## Phase C — implementation feedback / v0.11 (P1)
| Stage | Work | Acceptance |
|---|---|---|
| PR-16 | Controlled implementation preview capture, including explicitly isolated local target mode (not weakening public-reference SSRF policy), dynamic-region masks and viewport/state matched diffs | Known fixture diffs, dimensions/missing coverage reported; no network access beyond isolated target |
| PR-17 | Codex handoff: reviewable task, evidence index, selective fix tasks, iteration history and benchmark | Pilot on three authorized representative sites; compare tokens, elapsed time, repeated captures and visual coverage against baseline |
| PR-18 | GitHub publication reliability: live private sandbox smoke, manifest/changed-file review, idempotency, remote recovery, optional authorized individual-file publication | Draft PR with correct repo/branch/verified content; no unapproved push or auto-merge; no tokens in config |

## Phase D — v1.0 release (P2 until stability gates pass)
| Stage | Work | Acceptance |
|---|---|---|
| PR-19 | Desktop UX: integrated project navigation/export, contextual logs, import, graceful service lifecycle, upgrade checks | End-to-end from Applications without terminal for routine use; safe backup and rollback |
| PR-20 | Release engineering: versioned bundles, build hashes, dependency and license inventory, documented update/uninstall, signing/notarization if distributed | Reproducible personal build; external distribution only after signing/security review; clean and upgrade tests |

## Release gate
- Zero unexpected failures in Python, Rust, frontend, browser and Docker integration suites.
- Verified backup/restore, job recovery, bounded resource usage and explicit failure diagnostics.
- Real authorized captures + comparison + reviewed GitHub publication on disposable target.
- Native ARM64 installation, restart, upgrade and persistence validated.
- Evidence quality metrics: planned vs captured route/state coverage, verified hash rate, visual diff by state/viewport, repeated capture count, token/time benchmark. Baseline before claiming improvements.
- Maintain mandatory CONTEXT.md and AGENTS.md in every target; no unauthorized copying or destructive browser actions.

PR-10 accepted and merged. PR-11 deferred by user; backup/restore remains an unmet release gate. PR-12 security/build baseline is next, followed by PR-13 interaction coverage. Avoid marketing v1.0 or claiming measured token savings before gates pass.
