# Site Transfer Studio — итоговый технический отчёт MVP

Дата приёмки: 25 ноября 2026. Desktop version: 0.9.0. Статус: девять этапов приняты пользователем; PR #10 подготовлен к объединению с main по явному разрешению. Этот документ фиксирует приёмку, а не независимую сертификацию production-ready.

## Назначение
Evidence-first платформа для переноса авторизованных сайтов. Сначала собирает воспроизводимые материалы и измерения; затем предоставляет Codex компактное задание и доказательства вместо повторного исследования сайта. Не генерирует автоматически полностью готовый аналог сайта и не гарантирует 1:1 сходство.

## Архитектура
- Python 3.11+ core: config/schema, capture, measurements, manifest, comparison, pipeline, CLI.
- React 19 / TypeScript / Vite: единый Studio GUI, same-origin API.
- FastAPI / PostgreSQL 17 / Redis 7 / Celery: реестр проектов, состояния задач, очередь, persistent artifacts.
- Playwright Chromium 1.56.0: bounded same-origin discovery и desktop/mobile capture; worker выполняет браузерные операции.
- Tauri 2 / Rust: локальный контроллер macOS ARM64, отдельное окно Studio без нативных прав, фиксированные Docker operations. Docker Desktop обязателен. Данные в named volumes; конфигурация и экспорты в Application Support.
- GitHub: host gh CLI, явное согласие и SHA256 проверенного ZIP, новая ветка и draft PR в существующем private repo. Нет автослияния.

## Реализованные этапы
| Stage | PR | Результат |
|---|---|---|
| 01 Foundation | #1 | Schema, CLI, обязательные CONTEXT.md и AGENTS.md |
| 02 Docker/API | #3 | Локальный runtime, реестр create/list/read, persistence |
| 03 Web GUI | #4 | Создание/импорт и просмотр проектов, readiness |
| 04 Capture | #5 | Ограниченный discovery, скриншоты, история |
| 05 Design | #6 | Sampled layout, typography, colors, CSS/motion, hover |
| 06 Reference Kit | #7 | Inventory metadata, provenance, ZIP с документацией и хешами |
| 07 Comparison | #8 | Saved-run pixel diff, dimensions, sampled structural report |
| 08 Pipeline | #9 | Capture-to-kit, checkpoint ZIP, retry, cooperative cancel, reviewed publication |
| 09 Desktop | #10 | Native app/DMG build, local runtime management, Finder export |

## Результаты тестирования
Последний предоставленный Python log (PR-08): 60 collected, 59 passed, 1 skipped (Chromium not installed locally), 1 StarletteDeprecationWarning, 1.77 s. Все шесть новых pipeline/GitHub tests passed; публикация mock-only. Повторного Python прогона на PR-09 нет.
Rust log (PR-09): 6 passed, 0 failed. Apple Silicon, Rust/Cargo 1.100.0, Node 24.18.0, npm 11.16.0, Docker 29.9.3, Compose 5.7.1. Rust тесты покрывают .env/port validation, а не весь lifecycle.
Пользователь подтвердил 10/10 desktop acceptance: launch, existing PostgreSQL config, Start services, Open Studio, old projects/captures, new capture, Finder kit export, Stop/Start persistence, relaunch persistence, DMG build/check. Отдельные логи, хеши DMG и скриншоты приёмки не предоставлены. Проверки unavailable Docker, occupied port, clean install, upgrade/uninstall не входят в подтвержденные 10 пунктов. Результаты standalone Vitest отсутствуют.

## Контракт результата
Selected-run ZIP содержит README.md, AGENTS.md, CONTEXT.md, TASK.md, reference-kit.json и design/reference/ evidence: screenshots, route/capture manifests, доступные design reports/tokens, asset inventory. Хеши и scoped artifact paths обеспечивают проверяемость выбранного run. Не содержит автоматически скачанных сторонних бинарных ресурсов. Кодекс должен использовать существующие материалы, явно отмечать пробелы и снимать только недостающие доказательства.

## Известные ограничения и риски
- Сбор доказательств ограничен публичными авторизованными целями. Browser proxy не является полной изоляцией hostile content; redirect/network policy needs hardening. Нет localhost implementation capture; допускается сравнение сохранённых runs.
- Hover-only sample, не все click/menu/modal/scroll states; bounded DOM/CSS sampling, CSSOM gaps; structural comparison не гарантирует семантическое совпадение.
- Hard-kill, broker loss, stuck building требуют восстановления. Нет durable per-route resume, полной event log/reconciliation, гарантированного worker readiness. Kit retry reuse completed capture; не восстанавливает прерванный browser.
- Метаданные ресурсов не подтверждают лицензию; ZIP только выбранного run. Публикация private ZIP до 20 MiB, без live smoke test, без remote rollback.
- macOS использует существующие Docker volumes и .env; не переносит исходные файлы Docker volume в Finder. Native export — ZIP. Embedded browser tabs/downloads may need system browser. Нет Docker-free runtime, auto-update, подписи и нотарификации. Lockfiles и reproducible release procedure pending.
- No measured token/time savings, no verified multi-site benchmark, no public release/security assurance.

## Заключение
MVP 0.9.0 принят для персонального локального применения. Завершение девяти PR не означает полное исполнение каждого расширенного требования исходного SPEC или готовность к публичному распространению. Следующий этап — стабилизация и проверка реального Codex workflow перед расширением продукта. См. ROADMAP.md.

## PR-15 draft — capture quality
RE/MAX audit exposed white and incomplete evidence. Baseline/device shared readiness, scroll and PNG quality metadata are additive; invalid images are not registered. Existing run hashes, network and recovery contracts remain. See CAPTURE_QUALITY.md and CODEX_FEEDBACK_REMAXDELUX.md. Full regression, Docker GUI and production acceptance pending; do not claim release readiness.

PR-15 fixture coverage authored for delayed hydration/images, lazy/reveal, animation, overflow, invalid PNG, timeout, cancellation and old manifests. Explicit interaction PNGs also validated without changing the network gate. Execution pending.
