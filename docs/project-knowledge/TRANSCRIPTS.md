# P2 transcript contract

## Service and selection

`ingest.transcripts.ingest(Manifest, TranscriptStore, ...)` is the shared service.
P3 must call it from CLI/UI rather than implementing a second pipeline. Store paths
are explicit; callers can use Config.database and Config.data_dir / `canonical`.
No scrape command, export grouping, UI, agent extraction or later phase is added.

`CaptionAdapter.tracks(Video)` returns Track values; `fetch(Track)` returns bytes.
The optional YtDlpCaptionAdapter uses the existing `discovery` extra, extracts raw
metadata with download=False/process=False and requests only the selected caption
URL. Backend options disable video/audio, subtitle file writes, cache and side-file
writes, logs and backend retries. Selection and retry policy live in the service.
The native YoutubeDL/Request API was checked against official
[embedding documentation](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp) and
[YoutubeDL source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py),
then exercised with synthetic offline responses on locally installed yt-dlp.
This proves a local API contract, not live source accessibility.

Track requests allow only HTTPS youtube.com/googlevideo.com and their subdomains,
without URL credentials or nonstandard ports. Final response host is checked;
this is not a custom redirect transport or a claim of preventing all transport
redirects. Live-chat tracks are excluded. Request headers are never persisted.
Only available source-supplied tracks are used; no youtube-transcript-api fallback,
credentials, anti-bot bypass, media download or speech transcription is introduced.
Source-generated auto tracks may include translations; kind is a backend label.

Language list order takes precedence. Within a matching language: preferred kind,
exact code, JSON3/VTT/SRT format rank, language code and source position resolve
selection deterministically. Base codes accept regional variants; explicit locales
require that locale. There is no arbitrary-language fallback. Empty tracks,
unmatched languages and unsupported formats are distinct nonretryable issues.
`preference` is manual or auto, with the other kind as fallback.

## Canonical record

One schema-versioned record per stable YouTube video ID is stored in SQLite and
projected to `<video_id>.json`, never one record per export group or caption track.
It includes the original P1 Video data, all observed metadata/source IDs, discovered
manifest IDs, segments, track URL/language/kind/format/name, adapter name, payload
SHA-256, UTC retrieval time and original selection settings. Manifests retain full
P1 source results including original input URLs and source-level failures.

JSON3 events become segments with original event indices, start/end seconds and
original millisecond timing including the full text event and word offsets. VTT/SRT
retain original timestamp strings, cue IDs/settings and raw cue text/inline timing;
readable text decodes entities and removes markup. Control-only JSON3 events and
VTT NOTE/STYLE/REGION blocks have no transcript segments. UTF-8/Unicode text and
inert instruction content survive. Invalid UTF-8/unpaired surrogates, malformed
cues, nonfinite/negative offsets, reversed bounds and unsupported formats fail
explicitly. The caption payload is limited to 10 MiB. Empty tracks are unavailable.

Segments sort by start then original source index; overlaps and zero durations are
retained. Unverified discovery duration does not clip transcript timestamps.
New caption records explicitly initialize verification_status as unverified, even
if a constructed Video input has another status (retained in its source manifest).
No claim truth assessment occurs: verification_status remains unverified,
confidence unknown, visual dependencies not_assessed and content_trust explicitly
untrusted_source_text. Never treat caption text as instructions or verified facts.

## State, retries and recovery

Append-only migration v2 adds ingestion_manifests, transcripts and ingestion_jobs;
v1 remains unchanged. Manifest IDs are SHA-256 of deterministic full-manifest JSON.
One job per stable video ID records pending/running/succeeded/failed/unsupported,
lifetime attempts, safe classified issue and update time. `store.jobs()` exposes
failures; source-level problems without video IDs remain in the saved manifest.

A SQLite sidecar `<database>.lock.sqlite3` with BEGIN EXCLUSIVE serializes service
invocations on the local filesystem and releases its lock on process exit/crash.
Another worker fails before registering/resetting jobs. Internal store mutation
methods assume the service lock; they are not a standalone parallel-writer API.
Store paths resolve relative/symlink aliases before acquiring the lock.
Keep the database and lock paths stable; do not delete an active lock file or
use hardlink aliases to a database. Use
one canonical directory per database. Distributed/network-filesystem locks are
outside this phase's local-first scope.

Each attempt persists running state before remote access. Only classified network
or rate-limit failures retry automatically; max_attempts is 1..10 per invocation,
default 3, backoff capped at 60 seconds. Unknown/backend/private/unavailable/bad
caption failures remain visible; `retry_failed=True` explicitly reattempts permanent
failures. Interrupted running jobs are retried in the next serialized invocation;
already stored transcripts skip network calls. Successful selection is retained
when a rerun changes language/preference; P2 has no transcript replacement command.
New manifests and discovery observations are merged without losing earlier evidence.

SQLite saves canonical JSON and success together in one transaction before file
projection. Projection uses temporary files, fsync and atomic replace; it does not
follow an existing destination symlink. A crash between SQLite commit and file
replace is repaired on rerun without fetching captions. A file-write error returns
projection_failed and records a retryable storage_error job issue while preserving
the SQLite transcript. A rerun repairs corrupt/missing files from SQLite. SQLite
errors propagate and do not get mislabeled as remote errors. Corrupt SQLite data
requires restoring a backup; file repair is not database-corruption recovery.

## Verification and P3 handoff

Fixtures are original synthetic material, never real transcripts or UAT. Tests
cover parsers, selection, strict bounds/Unicode, safe host policy, optional backend,
native API mocks, upgrade/rollback, retries, interrupted jobs, idempotence, partial
batches, projection failures/repair, symlink replacement and worker exclusion.
See docs/test-reports/P2.md and docs/reviews/P2.md for actual gates/results.
Live YouTube, Python 3.11, minimum backend version and remote CI remain unverified.
P3 owns scrape/export CLI, Streamlit and grouping views over these canonical records.

P2 completed after separate AI follow-up approval: 104 tests passed independently,
including review-driven verification and database-alias regressions. No blocking
review issue remains. Final root gate evidence is recorded in the test report.

## P8 live-format repair

The real video PIt_02rTgx0 exposed JSON3 append-newline events (`aAppend=1`,
`segs` containing only newline) without dDurationMs. P2's original strict parser
rejected the whole transcript. The P8 repair recognizes only these durationless
newline controls, retaining raw events and original event indices under adjacent
segment `source_timing.formatting_events`. Leading controls attach to the first
text segment. No duration/end is fabricated; non-formatting text with missing
or invalid timing still fails. Synthetic parser and end-to-end regressions cover
this shape; real captions stay in ignored runtime storage. P2 history remains
unchanged; P8 test/review reports track this later maintenance change.
