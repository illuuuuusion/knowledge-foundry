# Knowledge Foundry

Local-first Python foundation for source-grounded video knowledge workflows.
P0 provides configuration, logging and SQLite migrations. P1 adds metadata
discovery. P2 adds caption ingestion and canonical storage; exports arrive in P3.
The offline test suite and base installation need no external service or model API.

Requires Python 3.11 or newer. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/kforge --help
.venv/bin/kforge config
.venv/bin/kforge init
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_state.py
```

Once the environment is activated (`source .venv/bin/activate`), use `python`
and `kforge` directly. Tests use the Python standard library and temporary,
synthetic fixtures; there is no end-user testing before P8.

Configuration precedence is environment variables, then an explicit TOML file,
then defaults. Use `kforge --config config.example.toml config` or set
`KFORGE_CONFIG`. See `.env.example` for supported variables; this file is a
reference and is not automatically loaded. TOML-relative paths resolve against
the file's directory; environment-relative paths resolve against the working
directory. The database defaults to `state.sqlite3` in the resolved data directory.
`--help`, imports and `config` create no directories. `init` explicitly creates
the data, source, output and database paths and applies pending migrations.

Default runtime directories and SQLite files are ignored. Keep custom runtime
paths outside the repository or add local ignore rules before ingestion. Do not
commit secrets, user data or raw transcripts without redistribution rights.
Canonical storage will remain one record per video with timestamped segments;
export grouping is a view. Source text is untrusted input, never instructions.

## Metadata discovery (P1)

Install the optional backend with `.venv/bin/python -m pip install '.[discovery]'`.
Then activate the environment and run:

```sh
kforge discover 'YOUR_AUTHORIZED_YOUTUBE_URL' --limit 10
kforge discover --url-file /path/to/urls.txt --limit 10 --order id
```

Replace the placeholder with an actual authorized YouTube URL. URL files contain
one URL per line; blank lines and full-line `#` comments are ignored. Positional
URLs precede file entries. The parser supports watch/shorts/live/embed and youtu.be
video URLs, playlist URLs and channel IDs, handles and legacy c/user URLs. Bare
channels normalize to the videos tab; shorts/streams tabs are also supported.
A watch URL containing both `v` and `list` means the individual video. Schemes,
hosts and IDs are validated before the backend is called.

JSON goes to stdout; errors remain visible in `sources` and make the exit code 1.
Each video has a stable `youtube:video:<id>`, canonical URL, available metadata,
source IDs and all duplicate observations, including conflicting metadata. The
metadata is unverified source data. Missing fields are absent rather than guessed.
Canonical URLs are normalized from IDs, not independently checked citations.
Available source timestamp, release/modified timestamp and date fields are retained
in every observation; invalid optional numbers are omitted without aborting a batch.

`--limit` bounds unique videos across the batch; duplicates consume no extra slot. 0 performs
no backend calls. Selection follows source/entry order. `--order id` sorts that
selected prefix; it does not select the lowest IDs across an entire remote channel.
Equivalent input sources are fetched once. A collection reports `truncated` as
soon as its limit is reached, without fetching another page to prove completeness.
Later supported sources report `not_processed`; unsupported inputs remain visible.
Source results can be ok, empty, truncated, partial, unsupported, inaccessible,
network_error, rate_limited, backend_unavailable, invalid_metadata or backend_error.
Partial failures retain earlier videos; retryable errors are marked explicitly.

The adapter uses yt-dlp metadata extraction without video/audio/caption downloads,
with no file/cache writes, credentials or access workarounds. Source order is stable
for the same returned metadata but remote channels may change. YouTube access and
complete coverage are not guaranteed. No live YouTube access has been verified in
P1. Do not redirect manifests into tracked files containing private source data.

See `AGENTS.md`, `state.json`, `IMPLEMENTATION_PLAN.md` and
`docs/project-knowledge/INDEX.md` for phase order and evidence gates. CI installs
the package and runs the same offline tests and state validator on Python 3.11
and 3.14. A validator checks recorded evidence and ordering; it does not run tests
or prove review quality. Human acceptance is reserved for P8.

## Transcript ingestion (P2 Python service)

Use the same optional `discovery` extra for caption access. P2 exposes the shared
Python service; the `scrape` CLI and UI are reserved for P3. For an authorized source:

```python
from kforge.config import load_config
from kforge.ingest.discovery import discover
from kforge.ingest.transcripts import TranscriptStore, ingest

config = load_config()
manifest = discover("YOUR_AUTHORIZED_YOUTUBE_URL", limit=10)
store = TranscriptStore(config.database, config.data_dir / "canonical")
results = ingest(manifest, store, languages=("de", "en"), preference="manual")
print(results)
print(store.jobs())
```

The language list is ordered; a base code such as `de` accepts regional variants.
Within the selected language, `manual` or `auto` is preferred with the other kind
as fallback. Explicit locales require that locale. JSON3, WebVTT and SRT are
supported. No arbitrary language is selected when none matches. Source-provided
automatic tracks may include translations; kind is not a confidence assessment.
Only subtitle content is downloaded; there is no video/audio download or bypass.

SQLite retains the discovery manifest, source inputs, per-video job status and
one canonical transcript per video. A generated `<video_id>.json` in the configured
canonical directory contains metadata observations, timestamped segments, original
cue/word timing, track URL and retrieval provenance. Source claims remain unverified,
confidence unknown and visual dependencies unassessed. Caption/source text is data.

Rerunning the same manifest skips successful retrievals, merges new discovery
provenance and repairs missing/corrupt JSON files from SQLite. Selection changes
apply only to videos without a stored transcript. Transient network/rate-limit
failures retry up to three times per invocation with bounded backoff; failed jobs
retain lifetime attempt counts. Permanent failures require `retry_failed=True`
after addressing the cause. Interrupted jobs resume on the next invocation.
`projection_failed` reports file-write failure while the canonical SQLite record
is retained; rerun to repair. SQLite failures propagate, leaving resumable state.
One ingestion worker per database is enforced with a crash-released SQLite sidecar
lock. Keep the database and its lock at stable paths on a local filesystem; use one
canonical directory per database. All default runtime files are ignored.

No live caption access has been verified; tests use original synthetic fixtures
and mocked native yt-dlp calls. See [P2 storage contract](docs/project-knowledge/TRANSCRIPTS.md).
