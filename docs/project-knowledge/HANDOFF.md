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

## P5 implementation and limits

P5 is explicitly authorized. `kforge consolidate` builds claims/evidence/nodes/
edges plus RESEARCH.md and research.schema.json; see [Graph](GRAPH.md). 164 tests
passed (155 prior + 9 P5). The separate reviewer requested changes twice (entity
false merges B1–B3) and approved round 3 after fixes and its own reproductions.
Its code-blind research smoke (synthetic page, no web access) produced an accepted
bundle on the first attempt. No live web research, model API, Python 3.11,
minimum dependency versions, remote CI or UAT were exercised.

## P6 next

Stop after P5 completion and commit until P6 is requested. P6 builds portable
packs from `output/graph/<domain>/` (claims.jsonl, evidence.jsonl, nodes.jsonl,
edges.jsonl) or by calling `graph.consolidate`. Keep each claim's citations (video
URL + start/end) and derived `verification_status`; never present `unverified` or
`contested` claims as facts. Entity node IDs can change between builds (merges),
so do not use them as stable public file names without a mapping. Packs must not
include raw transcripts or saved research texts by default; evidence quotes are
short excerpts. Known entity-merge limits: equal names merge despite conflicting
aliases; one entity aliasing two models merges them (N9). If TASK.md rules are
changed (e.g. an alias definition), bump `RESULT_SCHEMA_VERSION` deliberately.

## P6 completion verification

The user requested verification/completion of P6 followed by P7. The existing P6
implementation was staged but incomplete in state: the last recorded review still
requested changes for B3. The final implementation includes NFC/casefold realpath
guards and full-digest fallback for colliding topic names, with regressions.
The current AI reran all 172 tests successfully after reinstalling the package.
A new separate reviewer approved the actual final implementation after independent
tests and fresh path/collision reproductions (round 3). P6 is completed; state
advances to P7, which the user has also authorized. User testing stays disabled.
See KNOWLEDGE.md and the P6 test/review reports for the implementation contract,
review history and residual limits. No live access or user acceptance occurred.

## P7 implementation and verification

P7 is authorized by the same request as P6 verification/completion. It adds five
self-contained offline CLI integration scenarios and a temporary installed-wheel
smoke script; no application feature changes were necessary. See VERIFICATION.md
and docs/test-reports/P7.md for exact recovery behavior, coverage and limitations.
All 177 tests pass. Eight fresh-wheel console commands and 22-file installed
parity pass with reused dependencies. The isolated offline dependency attempt
failed for absent dependency wheels, and is explicitly not counted as passed.
The separate AI reviewer approved the actual diff, independently reran all 177
tests and the wheel smoke, and found no blocking issue. Reports and project
knowledge are finalized. P7 is complete; state advances to P8 and enables user
testing. P8 remains pending: no real UAT or user sign-off has occurred. The
current request ends with P7; do not mark P8 complete automatically. Next work
requires the real authorized workflow and explicit sign-off described in
`docs/uat/CHECKLIST.md`.

## P8 live trial support and parser maintenance

The user supplied video PIt_02rTgx0, reported shell parsing failures, then asked
the AI to execute the live workflow and build a small graph. A correct invocation
parsed, but German auto captions were rate-limited. The original English JSON3
response exposed durationless append-newline events that P2 had rejected. The
focused P8 repair and two synthetic regressions now retain those controls under
source_timing.formatting_events without inventing durations or relaxing spoken
text validation. See TRANSCRIPTS.md and the P8 test/review reports. Historical
P2/P7 approval evidence is unchanged; this is a later documented repair.

179 offline tests passed, independently rerun by the reviewer. The actual English
CLI then succeeded (1945 text segments, ten preserved formatting controls). Two
real AI-authored job results yielded nine selected unverified statements, 19 nodes
and 33 edges. No visual verification/external corroboration is claimed. Four
snapshot checks and independent source-range review passed. Outputs and a Mermaid
view live under ignored output/live-PIt_02rTgx0; the generated library also has an
identical temporary external copy at /private/tmp/kforge-knowledge-PIt_02rTgx0.

P8 remains in_progress and unsigned. docs/uat/REPORT.md records only the user's
reported CLI failures and the actual AI support run, not fabricated human UAT.
The parser fix/evidence remain uncommitted because the phase's explicit user
acceptance gate has not passed. Do not mark DONE or create the final P8 commit
without actual user sign-off. The German rate-limit and other external/client
verification limits remain explicit in the reports.

## P8 playlist/channel expansion

The user explicitly requested the same live workflow for a four-video playlist
and the entire northwestrepair channel. See LIVE_COLLECTIONS.md for source
semantics, runtime paths, precise outcomes and pending extraction coverage.
Playlist: 4/4 transcripts, repeated without refetch/duplicates, ten selected
claims and a 24-node/25-edge graph. Channel: all 448 discovered videos attempted
without cap, 432 transcripts exported, twelve without captions and four remaining
rate-limited. Resume preserved every prior successful payload hash/attempt count.

P8 additionally fixes /playlists channel navigation normalization and explicit
missing-tab classification. Three new synthetic tests bring the full suite to
182 passing tests; the separate reviewer approved the fixes. Four real-artifact
tests per corpus passed. Channel job generation covers all successful canonical
videos (468 jobs); only eight results are imported and 460 remain pending.
Selected graph: 21 unverified statements, six videos, 46 nodes/65 edges. No claim
of exhaustive AI extraction or user acceptance is made. Both library workspaces
have matching external temporary copies. P8 remains in progress and uncommitted
under the explicit user-sign-off gate.


## P8 user acceptance and final commit authorization

After the complete reported playlist/channel trial and disclosed limitations,
the user replied "Gut committe". This is recorded as explicit acceptance of the
presented scope and authorization to commit. The UAT report quotes that actual
message, while preserving the distinction between AI-run live checks and user
sign-off; no additional hands-on user test or external client session is invented.
P8 is completed and state advances to DONE. Existing independent repair/artifact
reviews remain approved; final tests/state validation precede the planned English
phase commit. Raw transcripts, runtime outputs, credentials and pending extraction
results stay out of Git. Accepted residual limits remain documented, including
16 inaccessible/rate-limited videos and 460 pending semantic extraction jobs.
