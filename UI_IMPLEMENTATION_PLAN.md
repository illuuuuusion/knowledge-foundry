# Knowledge Foundry — Native Desktop UI Implementation Plan

Status: **proposed / planning only**  
Repository: https://github.com/illuuuuusion/knowledge-foundry  
Codebase inspected: main, 2026-10-15  
Target: native GUI (no browser, HTTP server, Electron, Wine or Steam Proton)

## 0. Repo audit and decision

Existing code (reuse, do not duplicate):
- Python >=3.11 package; CLI in src/kforge/cli.py.
- src/kforge/ingest/{urls,discovery,transcripts,adapter,caption_adapter}.py parses YouTube links, lazily discovers metadata, persists one canonical transcript per video in SQLite, supports retries.
- src/kforge/workflows.py exposes synchronous scrape() / export() used by CLI and the optional Streamlit UI.
- src/kforge/export/transcripts.py exports markdown, txt, JSONL with 1/N/all grouping.
- src/kforge/builder/{jobs,graph}.py and src/kforge/knowledge/library.py produce agent jobs, graph and portable knowledge libraries.
- src/kforge/ui.py is Streamlit, not a native GUI.
- state.json reports legacy phases P0–P8 completed (current_phase DONE). Keep those facts unchanged.
- Existing schema migrations end at v3; src/kforge/storage.py owns migrations.
- TranscriptStore.session() uses a cross-process SQLite advisory lock: only ONE ingestion worker per database. Respect it.
- Source metadata can contain title/channel/upload date/duration, but values can be absent. Caption availability is not known until checking tracks; do not invent it.
- Explicit channel tabs /videos, /shorts, /streams are supported; /playlists navigation resolves to the regular video feed, NOT all playlists in that channel. Only explicit playlist URLs represent playlist contents.
- Current synchronous workflow returns a report only after finishing; real-time events, preflight selection, cancellation, durable UI queue and accurate ETA do NOT exist yet.

**Decision:** PySide6 + Qt Widgets. Add optional desktop dependency group and a native executable entry point. Build Windows/Linux/macOS packages per operating system (no Proton/Wine; do not require users to install Python when using a bundled distribution). Do NOT use QtWebEngine, Streamlit, localhost HTTP, Tauri, Electron or MCP. Keep the current CLI and optional Streamlit entrypoint backwards compatible.

Use model/view Qt tables (QAbstractTableModel + QSortFilterProxyModel), queued cross-thread signals, QSettings for GUI preferences, and existing Python domain services. GUI is a thin controller/view layer, not a second implementation of scraping or knowledge extraction.

## 1. UX concept / navigation

Main window: min recommended size 1100x720, resizable; system and dark theme; scalable typography and keyboard navigation.

    Knowledge Foundry                           [active job] [Settings]
    ┌──────────────┬────────────────────────────────────────────────────┐
    │ Dashboard    │ Workspace title     [Add URLs] [Import list]      │
    │ Sources      │ Search / filters / controls                       │
    │ Collection   │ ┌────────────────────────────────────────────────┐ │
    │ Transcripts  │ │ Virtualized table / detail panel               │ │
    │ Exports      │ └────────────────────────────────────────────────┘ │
    │ AI Jobs      │ Stage / throughput / ETA / errors / live events  │
    │ Knowledge    │ [Start] [Pause] [Resume] [Cancel] [Retry failed] │
    │ Activity     │                                                    │
    │ Settings     │                                                    │
    └──────────────┴────────────────────────────────────────────────────┘

Tabs/screens:

1. **Dashboard:** stored transcripts, currently active run, discovered/selected/succeeded/failed/skipped/cached, recent runs, quick actions; no fake lifetime analytics.
2. **Sources:** URL drop/paste/multi-line import; grouped video/playlist/channel source cards; validation, normalization, dedup warning, source limits; preflight discovery with video preview.
3. **Collection:** selection table, metadata filters, run options and queued jobs; separate streaming discovery from actual ingestion.
4. **Transcripts:** local SQLite-backed browsing, metadata, timestamp segments, source link, selection for offline re-export. Render all external text inert.
5. **Exports:** format checkboxes (Markdown/TXT/JSONL), grouping 1/N/all, selected video subset, destination, last artifacts, open output folder.
6. **AI Jobs:** domain profile, create/import extraction jobs, input/result counts/status; file-based agent instructions and folders. Do not claim jobs are executed by Claude/Codex automatically.
7. **Knowledge:** consolidate research graph; build portable library, domain, topic selection and token budget; show generated path and evidence/claims summary.
8. **Activity:** running/history table, exact stage, per-source and per-video status, log timeline, errors and retry actions.
9. **Settings:** app data location, config file, language priority, manual/auto caption preference, defaults/limits, UI theme, log level and permitted output folders.

Source intake: multiple independent video/playlist/channel URLs in one batch; paste from clipboard, drag-drop text/URL list, import UTF-8 .txt list; validate each locally before networking. Support saved named source collections as a later enhancement only if Phase UI3 includes durable persistence. Do not accept a search term/handle as a supported YouTube URL unless an explicit new parser feature and tests are added.

Preflight preview:
- discovery manifest snapshot with original inputs, canonical source identities, provenance and source issues;
- count unique videos after dedup across selected sources;
- per-video checkbox; select all/none/visible; show cached vs uncached based on SQLite;
- filter by source, literal title text, channel, video date (if available), duration (if available), already stored, source kind;
- category shorts/streams is based on explicit source tab and known evidence, NOT guessed solely from duration;
- date/duration unknown metadata remains visible under a clear "unknown" filter;
- choose global limit and optional per-source cap: document that channel order means feed order, NOT guaranteed "latest by upload date";
- show source truncation and unavailable tabs; not "fully discovered" when truncated;
- confirm selected IDs and settings before queuing; selection persists as an immutable run snapshot.
- no implicit crawling of a channel's playlist-navigation page.

Running monitor:
- phase: queued, discovering, ready, ingesting, exporting, generating jobs, importing, consolidating, building knowledge, complete/partial/failed/cancelled/interrupted;
- overall and per-video progress, completed/selected/cached/skipped/failed, failure type and retryable marker, successful transcripts, processed per minute, elapsed/remaining;
- current video and channel/source label, recent source/video events, timestamp, attempt number, next retry;
- ETA semantics below; visible run ID and exact input snapshot; searchable error detail; export artifacts with safe local open-folder action;
- accessible text status; never use color alone for state.

## 2. Critical architecture contracts

### 2.1 Headless backend event boundary

Introduce an optional, Python-only application service, e.g. src/kforge/app/:
- models.py: SourceSelection, RunSpec, RunSnapshot, ProgressEvent, RunStatus with versioned Pydantic/dataclass serialization;
- service.py: preflight(), submit(), run(), pause(), resume(), cancel(), retry_failed(), list_runs();
- events.py: EventSink protocol plus a no-op default, typed events;
- store.py: SQLite run/selection/event repository, migrations appended (v4+) and atomic status changes;
- eta.py: pure deterministic estimator;
- controller.py: serialization of one ingestion worker per DB and no blocking GUI calls.

Keep workflows.scrape()/export(), discovery and ingest callable as before, with opt-in callbacks/checkpoints or extracted composable services. CLI behavior and return codes must remain unchanged.

Do NOT implement progress by parsing stdout, tailing streamlit state, rereading generated files in a tight loop, or running a second scraping implementation.

Preferred service stages:
    validated URLs -> discover(snapshot) -> filtered selected manifest
    -> ingest(selected manifest) -> export(selected successes)
    -> optional jobs create/import -> graph -> knowledge

Important: selected manifest MUST preserve canonical video IDs, source observation provenance and only valid references. Discovery preview should be reusable as a snapshot; starting a run must not silently rediscover the channel and alter the selected IDs.

### 2.2 Durable run state (NOT project state.json)

Append SQLite migrations (do not edit prior migrations) for app_runs, app_run_sources, app_run_videos and app_run_events, or equivalent normalized tables. Persist run_id, immutable source/selection/options snapshot, timestamps, current stage, terminal counts, sanitized event IDs, last error and artifact paths. Reference existing canonical transcripts; do not duplicate their payloads.

Runtime transitions to consider:
    queued -> discovering -> ready -> running -> completed|partial|failed
                                  running -> pause_requested -> paused -> running
                                  running -> cancel_requested -> cancelled
    unfinished on restart -> interrupted -> resumable, never auto-start silently

One collection/scrape worker per configured DB; other operations may read snapshots, but concurrent graph/library writes to the same destination must be blocked. SQLite connections are thread-owned; only GUI thread mutates Qt models; data changes are delivered via queued signals.

### 2.3 Cooperative cancellation/pause/retry

- Check cancellation before each source/video and between retries; replace uninterruptible sleep with a cancellation-aware wait.
- Pausing means "finish current bounded external request, then pause"; make that explicit in the UI. Do not use unsafe QThread.terminate(), kill a thread or corrupt in-flight SQLite transactions.
- An interrupted run restores from persisted snapshot, deduping already saved canonical transcripts; never promise resuming inside a yt-dlp request.
- Retry only selected failed items; classify transient vs permanent, display failure reasons; respect capped retry/backoff and rate limits; no bot bypass.
- Default concurrency = 1 for ingestion due existing lock. Additional parallelism is OUT OF SCOPE until service/storage semantics explicitly support it.

### 2.4 Honest ETA

ETA is **unknown** during discovery when total work is not bounded or before enough duration samples exist. After known selection count and at least 3 terminal, noncached video attempts, calculate a rolling/robust rate (e.g. median or trimmed EWMA of recent per-video durations, sample window 10–30). Separate cached/skipped items and retry backoff from network attempts. Include outstanding scheduled backoff where known. Display "estimating..." or "unavailable" with reason if sample too small, source size changing or job paused. Recompute on each terminal video; throttle visual updates at <=2 Hz.

Display e.g. "about 12 min (rough estimate)", not fabricated countdown accuracy. Optional range based on observed p25/p75 or p50/p90 only with enough samples. For queued mixed-stage jobs, separate estimates by measurable stage; avoid a made-up overall percentage across incomparable discovery/agent tasks.

### 2.5 Safety and provenance

Inert text views; no embedded HTML or remote execution. Preserve video identity, timestamps, raw metadata observations, failures, verification status, visual dependencies, citations. Do not leak API keys, environment or raw third-party content into logs. Never mark an AI extraction job "processed" until a valid result is imported. A source report showing partial/failed remains visible despite successful exports. Validate output path/symlinks using existing library/export guards and show actionable errors.

## 3. Configuration and package boundaries

pyproject.toml:
- Keep optional [ui] Streamlit extra for compatibility.
- Add [desktop] PySide6 bounded major version and optional packaging extras; no mandatory Qt import from kforge core.
- Add kforge desktop command. Existing kforge ui continues to launch Streamlit, optionally documented as "legacy web UI"; no backwards-incompatible rename.
- Optional desktop executable entry point (e.g. kforge-desktop) should run the same application.

Suggested directory layout (adjust to project conventions, do not overengineer):

    src/kforge/app/{models,service,store,events,eta}.py
    src/kforge/desktop/{__init__,main,window,theme}.py
    src/kforge/desktop/screens/{dashboard,sources,collection,
                              transcripts,exports,ai_jobs,knowledge,
                              activity,settings}.py
    src/kforge/desktop/models/{sources,videos,runs,events}.py
    src/kforge/desktop/workers.py
    tests/test_app_service.py
    tests/test_app_eta.py
    tests/test_app_recovery.py
    tests/test_desktop_*.py
    scripts/smoke_desktop.py
    docs/project-knowledge/DESKTOP_UI.md
    docs/desktop-ui/UX_SPEC.md

Use Qt widgets and QAbstractTableModel, not one QWidget per row. Apply model updates via signals on GUI thread. GUI preferences in QSettings, but paths for the actual scraper/build engine must resolve using existing kforge Config semantics and an explicitly selected config profile; avoid changed-working-directory accidents in bundled builds. Show first-run data initialization, do not silently overwrite existing stores. Keep logs outside repository when packaged.

## 4. Workflow governance: extend state.json without rewriting history

Do not reset P0–P8 or change the historical top-level current_phase=DONE/user_testing_allowed=true. In UI0 add a new **desktop_ui** object in state.json, and extend scripts/validate_state.py to validate this independent track while keeping existing v1 state validation compatible. Proposed shape:

    "desktop_ui": {
      "current_phase": "UI0",
      "user_testing_allowed": false,
      "phases": {
        "UI0": {"status": "pending", "tests": {"status": "pending", "report": null},
                "review": {"status": "pending", "report": null},
                "knowledge_updated": false, "blockers": [],
                "planned_commit_message": "chore(desktop): establish native ui architecture"}
      }
    }

Repeat phase entry for UI0–UI9. Extend validation using shared phase-gate helpers or a separate desktop validator invoked by the root validator. UI user_testing_allowed must remain false through UI0–UI8, and become true only when UI0–UI8 are all completed; UI9 alone is real UAT. Keep the old top-level flag as historical P0–P8 state. Root validator MUST fail if either track is inconsistent. Its fixture tests must include old state, new state and blocked/incomplete paths.

Every phase gate:
1. Read state.json, this plan, AGENTS.md and relevant project knowledge.
2. Implement only the active UI phase.
3. **AI writes and executes** offline unit/integration/Qt headless tests, recording exact commands and outcomes in docs/test-reports/UIx.md.
4. Dedicated AI code review on actual diff, preferably separate agent, documented in docs/reviews/UIx.md. Blocking issues fixed; tests rerun.
5. Update docs/project-knowledge/DESKTOP_UI.md, DECISIONS.md/HANDOFF.md as needed and document unresolved limitations.
6. Update state.json only after tests, review and knowledge gates pass; run scripts/validate_state.py and full regressions.
7. Make an **English Conventional Commit** with NO Co-authored-by or other co-author trailers; verify git log -1 --format=%B.
8. STOP. Do not begin the next phase unless explicitly authorized in the controlling agent task. Never claim a review/test was performed when it was not.

Before UI9: no human/user acceptance test. AI-authored deterministic tests, simulated UI interaction, offscreen Qt smoke and controlled backend fixtures are permitted.

## 5. Ordered implementation phases

### UI0 — Architecture, governance and dependency isolation
Deliver: decision/UX spec, desktop extra, isolated desktop entrypoint skeleton, state.json desktop_ui track + validation; agreed service/events contracts; CLI/UI compatibility matrix.
AI tests: existing P0–P8 root suite, state validator old/new fixtures, CLI --help/base install with Qt absent, optional desktop import checks.
Review focus: no historical state rewrite; no mandatory Qt import; no old CLI regression.
Commit: chore(desktop): establish native ui architecture

### UI1 — Incremental backend orchestration and event instrumentation
Deliver: headless preflight and run service; stable progress event schema; selection manifest utility; instrument existing discovery/ingest/retry without changing default behavior; real events for source/video start/finish/error/cached.
AI tests: fake metadata/caption adapters; event ordering and count; source truncation; selection/provenance; failure during discovery; stdout/CLI parity.
Review focus: no duplicate scraper; event handling must not change canonical record hashes or lose provenance.
Commit: feat(app): expose observable collection workflows

### UI2 — Desktop shell and navigation
Deliver: native main window, sidebar, status bar, empty/loading/error states, theme, keyboard focus, responsive resizing, no-op/disabled features clearly labeled.
AI tests: PySide6 offscreen widget construction, navigation, Qt thread checks, optional dependencies, missing configuration.
Review focus: UI thread never calls a blocking network/service operation; no browser/server launch.
Commit: feat(desktop): add native application shell

### UI3 — Multi-source selection and metadata preflight
Deliver: multiline URL paste, file import, dedup cards, explicit tab support, asynchronous preflight, preview table, select/deselect and filters; named presets and reusing selected manifest, selected ID count and cached flags.
AI tests: mixed channel+playlist+video, alias dedup, invalid URLs, partial discovery, missing fields, filter semantics, no rediscovery after preview, no selection leakage to other runs.
Review focus: per-source/global limits and unknown metadata are honestly communicated.
Commit: feat(desktop): add source discovery and selection

### UI4 — Persistent queue, worker control and recovery
Deliver: DB v4+ run records, QThread worker/controller, queue with one ingestion worker, start/pause/resume/cancel/retry, persistence and restart recovery, offline view of run history.
AI tests: transition matrix, crash/restart simulation, lock contention, pause at safe boundary, canceled retry wait, stale preview, no duplicate storage, multiple instances same DB.
Review focus: transactions, thread ownership, safe cancellation, no corrupt canonical transcripts.
Commit: feat(app): persist and control collection runs

### UI5 — Live monitoring and ETA
Deliver: dashboard KPI tiles, per-source/per-video progress table, last events, source and error codes, retry attempts, elapsed, measured throughput, conservative ETA and history/activity screen.
AI tests: fake monotonic clock, <3 samples = unknown, cached items excluded, pausing, outlier protection, partial results, rate limits, undiscovered totals, UI stays responsive.
Review focus: numbers reconcile with SQLite; no false 100% on partial jobs, no imaginary ETA.
Commit: feat(desktop): add live run monitoring and eta

### UI6 — Transcript browser and export studio
Deliver: local canonical transcript list, search and detail view with timestamps, status/provenance; offline export selection, format grouping 1/N/all and destination/artifact actions; no networking for offline export.
AI tests: 1/N/all artifacts, empty selection, unknown ID, missing DB, unicode, dangerous/untrusted source text, path guards, existing CLI export parity.
Review focus: transcript content inert; original fields preserved, no accidental export of unrelated videos.
Commit: feat(desktop): browse transcripts and configure exports

### UI7 — Agent jobs, knowledge workflows and portable outputs
Deliver: domain profile selector/editor with validation; create jobs, list pending/imported/rejected/stale, open task folders; import result.json, consolidate graph, produce library and packs with budget/topic/output controls; show evidence statuses and warnings.
AI tests: complete synthetic CLI/service parity, rejected imported results preserved, external evidence failures, graph/library warnings, safe destination, missing profile, no proprietary API/MCP dependency.
Review focus: no implicit agent execution, no invented verified claims, source citation integrity.
Commit: feat(desktop): manage extraction jobs and knowledge builds

### UI8 — Distribution and comprehensive AI validation
Deliver: first-run assistant/settings, package scripts and OS-specific build workflows, app icons, logs, upgrade/migration safety, full docs/installation guide, accessibility baseline.
AI tests: full old+new suite, QTest/offscreen UI scenarios, end-to-end with synthetic fixtures, wheel and packaged smoke per available target OS, Qt absent in CLI, no GUI subprocess leak, first-run path handling, window-close mid-job.
Review focus: native installation requires no Proton/Wine or browser, Qt license/plugin notices, real limits of tested operating systems; leave untested targets explicitly unverified.
Commit: build(desktop): package and verify native application

### UI9 — Final REAL user acceptance testing (only now)
Gate: UI0–UI8 completed, automated tests passed, independent review reports and knowledge complete, desktop_ui.user_testing_allowed=true.
User flows: install and open app on intended OS; paste multiple channels/playlists/videos; inspect preview/filters; scrape a bounded authorized sample; observe ETA; pause/resume/retry; export N-to-1; create/import extraction jobs; build and open an external knowledge folder; restart and inspect retained status; check invalid/partial-source errors.
User sign-off required. Do not invent hands-on UAT or self-approve. Record docs/uat/DESKTOP_UI_CHECKLIST.md, docs/uat/DESKTOP_UI_REPORT.md and final issues. If user does not approve, keep UI9 incomplete.
Commit after approval: docs(desktop): record native ui acceptance

## 6. Acceptance criteria (release blocker checklist)

- Opens as a native desktop application without Streamlit, browser or local HTTP listener.
- Windows/Linux/macOS packaging documented; each platform called "verified" only after actual packaged smoke on that OS. Linux requires no Wine/Proton.
- Existing CLI, stored datasets and old P0–P8 state continue to work unmodified.
- Many mixed source URLs work in one collection with observable dedup and preflight selection.
- Source table and video selection accurately reflect backend capabilities, unknown fields and failure/truncation.
- Running tasks never freeze the UI; workers update GUI via signals.
- Durable runs survive app restart and can safely resume at video boundaries; only one ingestion writer per database.
- Pause/cancel/retry semantics are honest and safe; retries respect rate limits and existing retry contracts.
- Progress/ETA are measured, conditional and explicitly labeled estimates; no fabricated totals.
- Transcript exports support Markdown, TXT, JSONL and 1/N/all; artifacts are listed and safely opened.
- AI job, graph and portable library creation can be driven without a proprietary model API or MCP.
- All UI0–UI8 phases have AI-authored tests, independent review, updated project knowledge, valid state, and English no-co-author commits.
- Human acceptance takes place only in UI9.

## 7. Deliberately postponed

Parallel caption ingestion to the same DB, automatic all-playlists-of-channel crawling, subtitle availability prediction without checking tracks, media download/video vision, proprietary LLM automation, RAG server/MCP, notifications, cloud sync, multiuser collaboration, live GPU graph visualization, polished cross-platform auto-update system.

## 8. Agent start instructions

Use this document as the scope contract. First read AGENTS.md, state.json, scripts/validate_state.py, src/kforge/workflows.py, src/kforge/ingest/discovery.py, src/kforge/ingest/transcripts.py, src/kforge/ui.py, pyproject.toml and docs/project-knowledge/INDEX.md. Confirm the current baseline against main before making changes. Implement **UI0 only**. Write and run AI tests, request dedicated diff review, update knowledge/review/test reports/state and commit with the exact English message for UI0 and without any co-author trailers. Do not start UI1 unless separately authorized. No real user testing until UI9.
