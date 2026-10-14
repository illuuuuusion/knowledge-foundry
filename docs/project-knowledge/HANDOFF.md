# Phase handoff

## P0 scope and limitations

P0 is complete: installation succeeded, all 32 automated tests passed, and the
separate review agent approved the actual diff without blocking findings.
The reviewer independently reran tests, checked installed-source parity and
verified first-migration rollback/retry. Reports preserve the initial failed
installation and two corrected test failures as well as the successful reruns.
State advances to P1 with all later phases pending and user testing disabled.
The final validator and commit-message checks are required before delivery.

The repository began without commits or implementation. P0 creates package,
configuration, logging, migration foundation, CLI, CI and governance checks.
See `docs/test-reports/P0.md` and `docs/reviews/P0.md` for actual gate evidence.
The local virtual environment and runtime paths are ignored and not distributed.

The host has Python 3.14.8. Python 3.11 and remote GitHub Actions are not locally
verified. No YouTube requests, model calls, ingestion or real UAT were performed.
The P0 timebox is an estimate; satisfying evidence gates takes precedence.

## P1 authorization and scope

The initial start prompt stopped after P0. The user subsequently authorized P1.
P1 implements URL parsing, streamed metadata discovery, structured manifests and
the discover CLI with deterministic offline fixtures. See [Discovery](DISCOVERY.md)
and the P1 test/review reports for semantics and evidence. No transcript ingestion,
SQLite domain migration or real user acceptance is part of P1.

P1 is complete: optional backend installation/native offline contract succeeded,
all 64 tests passed, and the separate AI review approved the updated actual diff.
The initial review found discarded temporal metadata and advised an overflow fix;
both are resolved and retained in the review history with regression evidence.
The final implementation preserves source dates/timestamps and every conflicting
observation, and malformed optional numbers do not abort remaining collection
entries. State advances to P2 with user testing disabled. Live YouTube access,
Python 3.11, minimum backend version and remote CI remain unverified.

## P2 next

After P1 approval and gates, advance to P2 and stop until it is requested. P2 adds
caption-track selection, normalization, per-video canonical records and resumable
SQLite ingestion state. Preserve discovery source IDs, original input URLs and
metadata observations. Transcript timestamps and provenance must survive every
transformation. Export grouping remains a view and belongs to P3. Keep unavailable
sources explicit; do not assume complete YouTube coverage or implement bypasses.

Use the documented .venv install/test commands; re-install the package after code
changes before testing installed behavior. Reports and a separate AI review are
required before phase completion. Add ignores for custom paths kept in the repo.

## P2 implementation and limits

P2 is explicitly authorized by the user. Caption selection/normalization and
resumable canonical storage are implemented; see [Transcripts](TRANSCRIPTS.md).
The initial full run passed 101 tests. An additional malformed Unicode regression
brought the suite to 102 passing tests. The initial separate review requested a
caption verification-status fix and advised resolving database aliases for worker
locking. Both are now fixed with regressions; 104 tests passed after rebuild.
The same separate reviewer approved the updated actual diff, reran all 104 tests
and confirmed status isolation, cross-process original/symlink worker exclusion
and installed/source parity. No unresolved blocking issue remains. Reports and
project knowledge are updated; P2 completes and state advances to P3 for handoff
only, with user testing still disabled. Final validator/commit checks are recorded
in the test report. No P3 implementation is authorized by this P2 request.

The shared Python API accepts the P1 Manifest and configured SQLite/canonical
paths. SQLite retains source manifests, jobs and one normalized transcript per
video, with JSON projections repairable offline. Retries, permanent failure
recovery, interrupted jobs and worker exclusion are covered by offline fixtures.
No live source access, fallback API, media download, later-phase feature or real
UAT was performed. P3 must expose the same service through CLI/UI and treat
export grouping purely as a view. Language/preference changes do not replace
already successful captions; consult the explicit storage/recovery contract.

## P3 next

Stop after P2 completion and commit. When requested, P3 adds scrape/export CLI,
Streamlit and Markdown/TXT/JSONL grouping views over the canonical transcripts.
Read TRANSCRIPTS.md first: reuse the service and preserve source evidence, all
timing and explicit uncertainty. A persisted-manifest reload convenience API can
be added if the P3 workflow needs it; P2 snapshots already retain the inputs.

## P3 implementation and limits

P3 is explicitly authorized. Shared scrape/export workflows, CLI, deterministic
Markdown/TXT/JSONL grouped views and local optional Streamlit are implemented.
See [Exports/UI](EXPORTS_UI.md). All 145 tests passed, including all 104 prior
regressions and native UI contracts using mock services. The separate AI reviewer
approved the actual staged diff with no blocking findings, independently reran all
145 tests and confirmed installed-source parity for 19 files. Additional offline
checks verified full Unicode/extensions, unchanged SQLite bytes and protected
Markdown output. Review/test reports and knowledge are finalized; P3 completes
and advances to P4 for handoff only, with user testing still disabled. Final root
suite/state/commit checks are recorded in the test report.

Exports retain complete canonical/source data without network calls; SQLite stays
per-video. Local UI startup/health was checked with AI-controlled temporary config,
no sources and automatic server cleanup. No real UAT, live YouTube access, Python
3.11, minimum backend/UI dependency version or remote CI was performed. P4 remains
pending and must not be implemented under this request.

## P4 next

Stop after P3 completion and commit until P4 is requested. P4 introduces file-based
extraction jobs/config/schema, output validation/import and source cross-reference
checks. Reuse the canonical/snapshot contracts, retain all timestamps/provenance,
never treat source text as instructions and never label unsupported claims verified.
No extraction jobs or other P4 behavior were implemented under the P3 request.

## P4 implementation and limits

P4 is explicitly authorized. Domain YAML, Pydantic result schema, deterministic
job writer, validating importer and migration v3 are implemented; see
[Jobs](JOBS.md). 155 tests passed (145 prior + 10 P4). A separate reviewer
subagent approved the staged diff without blocking findings and completed a code-blind
job-agent smoke on a synthetic job. Non-blocking follow-ups were applied or
documented and confirmed in the review follow-up. No live source, model API,
Python 3.11, minimum dependency versions, remote CI or UAT were exercised.

## P5 next

Stop after P4 completion and commit until P5 is requested. P5 consumes
`extraction_results` payloads: select only rows whose job ID is in the current
`plan(read_snapshot(...), domain)` (older rows remain after settings changes or
transcript replacement). Citations are source ID + start/end seconds; resolve them
to canonical segments for provenance. Claims arrive `unverified` with agent
confidence and visual dependency; P5 adds external evidence and must never promote
an observation to verified without it. Bump `RESULT_SCHEMA_VERSION` if result
schema, TASK.md rules or validation change.
