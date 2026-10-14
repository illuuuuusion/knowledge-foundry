# P3 exports, workflows and Streamlit

## Shared orchestration

`workflows.scrape(Config, urls, ...)` validates export/language choices, calls P1
`discover`, P2 `ingest` and the P3 offline exporter. It returns ScrapeReport with
manifest, per-video ingestions, exports and has_errors. A scraped batch exports
only its successful or SQLite-committed projection_failed videos; failed captions
and source failures remain visible. Cached captions are reused, but repeated scrape
still discovers sources. CLI and UI directly call the same `workflows.scrape` and
`workflows.export` services; there is no second ingestion/export implementation.

P3 changes the shared P0/P1 CLI boundary and adds optional UI packaging/CI extras;
all 104 earlier tests must pass again. No P2 applied migration or caption logic was
changed. P4+ orchestration, research, extraction, graph and packs remain pending.

`kforge scrape` accepts positional URLs and --url-file, --limit/--order,
--language (repeated), --preference manual|auto, --retry-failed and export options.
`kforge export` is offline, optionally accepts repeated stable --video-id values,
and defaults to all stored records. Both emit JSON status. Scrape returns 1 for
partial/source/video failures, 0 otherwise; invalid argparse input returns 2.
Runtime/storage/selection errors return 1 without tracebacks. CLI `ui` launches
installed ui.py through the same interpreter's Streamlit, local-only, with
telemetry disabled, optional port and forwarded TOML configuration.

## Read-only export snapshot

`export.transcripts.read_snapshot` opens SQLite in URI mode=ro and an explicit read
transaction. No init, migration, backend import/request, caption download, canonical
file write or file-repair operation occurs. Schema must already be current (v2).
Missing storage is an error; an empty initialized database produces zero exports.
Unknown requested IDs fail, rather than silently omitting requested videos.

Each envelope has schema_version=1, the entire canonical `record` and a map of all
linked `source_manifests`. These include original input URLs, discovery source
status/failures and every P1 metadata observation, so manifest IDs remain resolvable.
Read-time checks cover identity, required rendering/provenance fields, segment
order/bounds, UTF-8/finite JSON and manifest SHA-256 integrity. Record extensions
are preserved. This is validation, not a verification of transcript claims.

Views always sort by stable video ID and partition exactly once by a positive
integer or all. No grouped record is written back to SQLite; segment offsets remain
relative to their own video and overlap/zero-duration evidence survives. JSONL has
one complete envelope per physical line. Markdown and TXT provide readable text
and a complete JSON envelope, preserving even unknown metadata and raw timing.
The lossless section intentionally duplicates readable text; this modest MVP
tradeoff keeps exports independent and source references self-contained. Linked
full discovery manifests may duplicate collection metadata across videos.

Markdown source URLs and segment text are literal code blocks; dynamically sized
backtick fences prevent caption fence injection. Titles become one escaped heading
line; original titles/content remain exact in the complete envelope. Verification,
confidence, visual dependency and source-trust markers remain explicit. These are
local authorized raw-transcript views, not P6 shareable knowledge libraries.

## Output paths and recovery

A full SHA-256 over selected envelopes, normalized formats and group size identifies
`output_dir/transcripts-g<size>-<digest>/`. Group files contain only an index and
validated first/last ASCII video IDs plus fixed format extension. Titles and source
paths never control file paths. Format selection is deduplicated in fixed order
markdown/txt/jsonl. Identical inputs/settings yield identical paths/bytes; changing
settings/content gets another batch so older group layouts do not masquerade as
current results. The report lists precisely the current artifacts. Prior batches
remain available and automatic pruning is not implemented.

The configured output root is a trusted explicit local path (resolved); generated
batch-directory symlinks are rejected. File writes use temporary files, fsync and
atomic replace, replacing rather than following destination symlinks. A failed
write cleans its temporary file and does not mutate canonical SQLite data. Atomicity
is per file, not whole batch: earlier files may remain after a later write fails.
Rerun the same export to repair/finish. Concurrent identical exports write identical
content atomically. Deliberate concurrent path/parent replacement is outside this
local trusted-output operating model. No export index or standalone JSON/SRT/VTT
output is added; JSONL and lossless JSON sections meet the P3 requirements.

## Optional UI and automated contracts

`ui.render(st)` loads config without initializing storage. Two Streamlit forms
separate collect/export and stored-only export. Widgets gather source URLs, bounded
video limit, comma-separated language priority, caption preference, group size,
formats and permanent-failure retry. Only form submits invoke shared services;
normal reruns retain last reports. Failed collection clears stale success output.
Storage-config changes clear old reports. Status tables contain source/job issues
and artifact paths without rendering untrusted transcript/metadata HTML. No browser
source preview/download or hosted account/service is required by P3.

Streamlit is optional (`ui` extra, >=1.40,<2); base Python/CLI retains no mandatory
runtime dependencies. The API choices were checked against official
[forms documentation](https://docs.streamlit.io/develop/api-reference/execution-flow/st.form),
[app-running documentation](https://docs.streamlit.io/develop/concepts/architecture/run-your-app)
and [AppTest API](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
Locally installed Streamlit 1.66.0 executes actual AppTest scripts with synthetic
mock services/adapters, covering controls, submits, reruns, partial failures,
configuration/storage errors and offline export. These are AI tests, not UAT.
`scripts/smoke_ui.py` is the persisted AI-controlled local-launch/health smoke;
it uses temporary config, no sources and terminates its own process group.

## P4 handoff and remaining limits

Only P3 is authorized in this request. P4 can consume `read_snapshot` or canonical
records for extraction jobs; source text remains untrusted and claims unverified.
Do not use export grouping as storage mode. A public saved-manifest reload/resume
helper remains optional; P3 relies on fresh discovery for scrape and SQLite for
fully offline export. Existing successful caption selection remains P2's policy.
No live YouTube, real browser/user testing, minimum Streamlit/yt-dlp version,
Python 3.11 or remote CI was verified locally. See P3 test/review reports for gates.

P3 is complete following separate AI review approval, 145 passing tests and
finalized project knowledge/test/review evidence. No blocking findings remained.
Read the test report for final root gate commands; P4 remains unimplemented.
