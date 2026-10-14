# Implementation plan — Knowledge Foundry MVP

## Scope and delivery target

One-day, local-first MVP (approximately 8 hours **if third-party access and agent tooling cooperate**). This is a best-effort target, not a guarantee. Focus on a vertical slice: source -> normalized transcript -> configurable export -> agent file jobs -> curated portable knowledge pack.

**In scope:** one Python monorepo, CLI plus small Streamlit UI, local SQLite and files, public/authorized YouTube URLs, manual/auto subtitle preference, resume/error states, Markdown/TXT/JSONL exports, source-grounded agent extraction jobs, research intake as source files, simple graph JSONL, Markdown knowledge packs for Claude/Codex.

**Deferred:** distributed tasks, accounts, Neo4j, vector database, embeddings, direct paid LLM integration, full visual video analysis, GPU hardware-specific truth validation, automated web browsing engine, automated audio transcription, full-scale channel crawling reliability, and a public multiuser platform.

**YouTube and IP boundaries:** use legitimate, permitted source access; do not promise complete channel coverage. Keep raw source material out of distributable output by default. Knowledge sharing requires review of copyright, licenses and use permissions.

## Phase completion protocol (required for EVERY phase)

1. Set active phase to `in_progress`, leave later phases `pending`.
2. Implement acceptance criteria with narrow changes.
3. AI writes/revises automated tests and runs them (unit/integration/fixture-based E2E as appropriate). Save actual command, pass/fail counts and any limitations in `docs/test-reports/PX.md`.
4. A **different AI reviewer when available** reviews the actual git diff, tests, robustness, provenance/security and scope. If no separate agent is available, use a dedicated review-only pass and explicitly record that it was not independent. Save findings and verdict in `docs/reviews/PX.md`.
5. Fix all blocking review issues, rerun affected tests, repeat review until `approved`. Never fabricate or assume a review.
6. Update `docs/project-knowledge/` (decision log, lessons, relevant architecture/risks, handoff).
7. Mark tests `passed`, review `approved`, knowledge updated `true`, and phase `completed` in `state.json`. Advance `current_phase` to the next incomplete phase. Set `user_testing_allowed` to true ONLY after P0–P7 all complete.
8. `python scripts/validate_state.py` must pass; then create the planned English Conventional Commit without co-author trailers. Confirm git status and message. Do not modify a completed phase without documenting the reason and rerunning gates.

**No human user acceptance tests before P8**. AI-authored automated testing must take place continuously. AI smoke tests against a permitted external source may be performed before P8 when environment permits, but must be non-interactive and clearly marked as non-UAT.

## Phase sequence

### P0 — Foundation and governance (25 min)

**Build:** pyproject and installable Python package, `kforge` CLI skeleton, modular directories, SQLite migration strategy, configuration/env handling, `.gitignore`, logging, CI (where GitHub is used). Keep source/data/output paths configurable.

**AI tests:** state validator positive/negative cases, package import, CLI help, config defaults. No real YouTube requests.

**Accept:** scaffold installs, CLI help runs, state validator and project test command pass. No secrets/traces in repo.

**Commit:** `chore: initialize project structure and workflow`

### P1 — Source discovery (45 min)

**Build:** URL parser for YouTube video, channel, playlist and URL list; source discovery service behind an interface (yt-dlp metadata first), filter by `limit`, stable ordering, duplicates and output metadata. Implement clear unsupported/inaccessible states.

**AI tests:** URL parameter fixtures, mock channel/playlist pagination, deduplication, limit and sorting, empty results, unsupported links, network error classification.

**Accept:** structured video manifest with stable IDs for every supported source type. No transcript fetching in this phase.

**Commit:** `feat(ingest): discover videos from supported URLs`

### P2 — Transcript retrieval and canonical storage (75 min)

**Build:** adapter for available manual or automatically generated subtitle tracks, language selection, normalizer preserving segment timestamps and source URL, per-video canonical JSON, SQLite manifest/job state, retries and resumability. Optional youtube-transcript-api fallback; never download video/audio by default.

**AI tests:** subtitle fixture parsers, manual-vs-auto preference, unavailable captions, repeated ingestion idempotence, retry classification, Unicode, transcript segment order and bounds, resume from interrupted jobs.

**Accept:** a rerun does not duplicate successful videos; failed/unsupported videos are visible and recoverable; all time offsets remain traceable.

**Commit:** `feat(ingest): normalize and persist transcripts`

### P3 — Exporters and lightweight UI (65 min)

**Build:** CLI commands for `scrape` and `export`; outputs Markdown/TXT/JSONL from canonical data; `--group-size 1|N|all`; Streamlit page for source, video limit, preferred language, transcript preference, export grouping and status. JSON output optional if time permits. If SRT/VTT is added, keep it per-video to avoid invalid concatenation.

**AI tests:** exact grouping of 0/1/N/many transcripts, deterministic filenames and ordering, JSONL readability, Markdown metadata, zero data loss, sanitized paths, UI smoke/contract tests with mocked services.

**Accept:** re-export works offline without redownloading; UI and CLI call the same underlying Python functions.

**Commit:** `feat(export): add configurable transcript exports`

### P4 — File-based AI knowledge extraction jobs (65 min)

**Build:** domain YAML configuration, Pydantic extraction schema, job writer (`TASK.md`, `input.jsonl`, `schema.json`), result importer, schema validator and source cross-reference checks. Primary mode: Claude/Codex processes files interactively or via supported CLI; no required model API.

**AI tests:** deterministic job partitioning and naming, valid output import, malformed JSON rejection, missing source ID rejection, missing/invalid timestamps, prompt-injection fixture treated as untrusted text, resumed jobs.

**Accept:** agent can read one job, create a valid result, importer accepts valid results and rejects unsupported/uncited claims. Model invocation itself remains outside deterministic test suite.

**Commit:** `feat(builder): introduce file-based extraction jobs`

### P5 — Evidence enrichment, consolidation and graph (60 min)

**Build:** ingest agent-supplied internet research documents/URLs and retrieval metadata, merge equivalent entity aliases, preserve conflicting statements, emit claim/evidence records plus `nodes.jsonl` and `edges.jsonl`. Web research is performed by a capable agent using permitted web access; automated browsing infrastructure is NOT required for MVP.

**AI tests:** dedup, conflict retention, provenance graph consistency, invalid reference detection, model/revision disambiguation, missing evidence rejection, no promotion of observation into verified fact.

**Accept:** every claim can be traced to video timestamps or external documents and has explicit verification status. Graph has no dangling edges.

**Commit:** `feat(builder): consolidate evidence and graph relations`

### P6 — Agent-ready knowledge packages (65 min)

**Build:** output folder separate from application repo with `INDEX.md`, hierarchical `topics/`, `procedures/`, `references/`, `graph/`, `packs/`, `AGENTS.md`, `CLAUDE.md`; presets `essentials`, `topic`, `full` with approximate configurable token budget. Generated files include provenance references and explicit uncertainty.

**AI tests:** index-to-file link integrity, export pack content/cap behavior, Markdown escaping, deterministic rebuild, path traversal prevention, source references, no raw transcripts in public/shareable package by default.

**Accept:** generated library can be opened as a separate Codex/Claude Code workspace or files can be uploaded selectively to Claude Projects. Instructions tell agents to consult `INDEX.md` and not load everything.

**Commit:** `feat(knowledge): generate agent-ready knowledge packs`

### P7 — AI integration and regression verification (45 min)

**Build:** offline fixture covering discovery -> canonical transcript -> grouped export -> agent job -> imported result -> graph -> portable pack; CLI smoke; docs for installation and running; failure/resume recovery; test report and independent review. Resolve blocking gaps but do not add unrelated features.

**AI tests:** AI-written end-to-end scenario with stub adapters, integration between the two products, corrupt input recovery, security/no-secrets assertions, clean-install smoke (when environment permits). Explicitly list anything not externally tested.

**Accept:** reproducible AI test suite passes; README and scripts work; documented limitations and residual risks. All earlier phases approved.

**Commit:** `test: complete automated end-to-end verification`

### P8 — Final USER acceptance testing ONLY (35 min)

**Now and only now:** set `user_testing_allowed = true` after P7 completion. User performs real workflow: choose an authorized channel/playlist/single video, select N and grouping, confirm outputs, run Claude/Codex file job, import and inspect generated GPU repair knowledge, verify that a separate workspace can discover and cite sources. Record issues and screenshots/notes as appropriate in `docs/uat/REPORT.md`.

**AI contribution:** author UAT checklist in advance; support debugging and add regression tests for discovered defects, run code review after fixes. Any implementation fixes require passing AI tests + review before phase completion.

**Accept:** user signs off explicitly; no automatic sign-off, no fabricated user result. If UAT cannot be performed, keep P8 incomplete.

**Commit:** `docs: record final user acceptance results`

## Definition of Done

All P0–P8 phase gates passed; AI test reports and documented code reviews exist for every phase; the real UAT sign-off is recorded; `state.json` has `current_phase: DONE`; code has no co-author trailers; raw transcripts are not committed; and a separate Knowledge folder can be read by a file-capable Claude/Codex client.

## Manual runbook after P7

See `docs/uat/CHECKLIST.md`. Do not run it with the user before P8.
