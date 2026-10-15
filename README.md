# Knowledge Foundry

Local-first Python foundation for source-grounded video knowledge workflows.
P0 provides configuration, logging and SQLite migrations. P1 adds metadata
discovery. P2 adds caption ingestion and canonical storage; P3 adds grouped exports
and a local Streamlit interface. P4 adds file-based agent extraction jobs; P5
consolidates claims, agent research evidence and a graph; P6 builds portable,
agent-ready knowledge libraries and packs.
P7 verifies the complete offline CLI workflow, recovery and installed packaging.
The offline test suite and base installation need no external service or model API.
Runtime dependencies are Pydantic and PyYAML (P4 schema and domain configuration).

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
and `kforge` directly. Tests use the Python standard library unittest and temporary,
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
Python service; the P3 `scrape` CLI and UI use that same implementation. For an authorized source:

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

## CLI and local interface (P3)

After installation and environment activation:

```sh
kforge scrape 'YOUR_AUTHORIZED_YOUTUBE_URL' --limit 10 --language de --language en --preference manual --group-size 2 --format markdown --format jsonl
kforge scrape --url-file /path/to/urls.txt --limit 10 --retry-failed --format txt
kforge export --group-size all --format markdown --format txt --format jsonl
kforge export --video-id youtube:video:YOUR_VIDEO_ID --group-size 1 --format jsonl
```

Replace placeholders with an actual authorized URL/video ID. `scrape` discovers,
ingests and exports only its selected batch; successful videos already in SQLite
skip caption retrieval. Discovery still runs on repeated scrape commands. Permanent
caption failures require `--retry-failed`; transient retries follow P2's policy.
`--language` may be repeated in priority order (default en); manual/auto preference
has the other kind as fallback. Limit/order/URL-list behavior matches `discover`.
JSON status goes to stdout. Partial failures retain successful data and return
exit 1 with source and video issues; successful operations return 0. Invalid
argparse options return 2. Exports do not change canonical storage.

`export` reads stored transcripts and manifests offline, even when generated
canonical JSON files are missing. It never discovers sources, fetches captions,
migrates a database or repairs canonical files. Run `scrape` or `init` before
exporting from a new store. Default selection is all stored transcripts; repeat
`--video-id` to select a subset. Unknown IDs or corrupt/missing provenance fail
explicitly. Empty initialized storage exports zero files.

`--group-size 1`, a positive integer N, or `all` partitions videos sorted by stable
ID; timestamps stay relative to each original video. Repeat `--format` to request
Markdown, TXT and/or JSONL (default Markdown). JSONL contains one envelope per
video with `record` and `source_manifests`; Markdown/TXT include readable segments
and a complete JSON provenance section so original metadata, text and timing are
retained. These are authorized local transcript exports, not shareable knowledge
packs; redistribution permissions still apply. P6 governs portable knowledge packs.

Generated paths are under the configured output directory, in a deterministic
`transcripts-g<size>-<content hash>/` batch folder. File names use a group index
and validated first/last video IDs, never source titles. Identical re-export keeps
paths and bytes stable; changed selection/grouping/formats/content gets another
batch folder so earlier outputs remain available. Source text is untrusted, claims
remain unverified and confidence/visual dependencies are not assessed. Markdown
keeps source content in code blocks with fences that source text cannot close.
Individual files are replaced atomically; a failed multi-file export may retain
already written files and can be rerun safely. SQLite is not modified by export.

Install and start the optional UI:

```sh
.venv/bin/python -m pip install '.[ui,discovery]'
.venv/bin/kforge ui
# Optional: .venv/bin/kforge --config /path/to/config.toml ui --port 8502
```

The UI listens on 127.0.0.1 (default port 8501), with usage telemetry disabled by
the launcher. It provides source URLs, video limit, ordered languages, transcript
preference, export group size/formats, retry control and source/video/export status.
An additional form exports all stored transcripts offline. Widget changes do not
collect captions until the form is submitted. Output tables show local files;
open those files in your chosen editor. CLI and UI use the same workflow functions.
This local app is not a public multiuser service. Installation/start instructions
are preparation; real user acceptance remains reserved for P8.

The offline suite includes native Streamlit AppTest with mocked source adapters
when the ui extra is installed; tests skip that optional native UI group without
Streamlit. CI installs ui/discovery extras to exercise the entire suite. See
[P3 export/UI contract](docs/project-knowledge/EXPORTS_UI.md),
[P3 test report](docs/test-reports/P3.md) and [P3 review](docs/reviews/P3.md).

## Agent extraction jobs (P4)

A domain YAML file (see `domain.example.yaml`) defines the domain ID, title,
guidance, allowed entity types and claim kinds, and an approximate character
budget per job. It is trusted local configuration. After `scrape` (or `init` on
an existing store, which applies migration v3):

```sh
kforge jobs create domain.example.yaml            # optionally --video-id youtube:video:ID
# Let Claude Code/Codex open one job folder, read TASK.md, and write result.json.
kforge jobs import domain.example.yaml
```

`create` is offline and writes `output/jobs/<domain>/<job_id>/` with `TASK.md`,
`input.jsonl` (untrusted transcript segments with source ID, URL, source index
and start/end seconds) and `schema.json` (generated from the Pydantic result
model). Each video is partitioned separately in segment order; a job ID is
`<video id>-<part>-<hash>`, where the hash covers the input, domain settings and
result schema version. Reruns rewrite identical files and never touch an existing
`result.json`; changed domain settings produce new job IDs instead of reusing
results produced under other instructions. No model API is called.

`import` validates each `result.json` against the schema and against the trusted
canonical input from SQLite (never the job's own files): every claim needs at
least one citation whose source ID is in the job and whose start/end lie within
and overlap the job's segments; kinds, entity types and entity references must
match the domain; `verification_status` must be `unverified`. A result is
accepted or rejected as a whole. Accepted results go to SQLite table
`extraction_results` with domain, job input hash and result hash. Unchanged
results are skipped, a rejected replacement keeps the earlier accepted result,
and folders from older settings are reported as `stale`. Statuses are `pending`,
`imported`, `unchanged`, `rejected` (with error locations, exit 1) or `stale`.
Run `import` with the same working directory/configuration as `create`; without a
job folder for the domain it fails with exit 1. Deleting an imported result.json
shows `pending`, but the stored result remains in SQLite.
Transcript text stays data: TASK.md contains only trusted configuration, IDs
and numbers, and imported claims remain unverified for P5 evidence work.

## Evidence consolidation and graph (P5)

```sh
kforge consolidate domain.example.yaml
# Let an agent with permitted web access follow output/graph/<domain>/RESEARCH.md
# and write research bundles to sources/research/<domain>/*.json, then rerun:
kforge consolidate domain.example.yaml
```

`consolidate` is offline and deterministic. It reads the imported extraction
results of the *current* jobs (results of older job IDs are ignored) and every
research bundle in `<source_dir>/research/<domain>/`, then rewrites
`<output_dir>/graph/<domain>/` with `claims.jsonl`, `evidence.jsonl`,
`nodes.jsonl`, `edges.jsonl`, `RESEARCH.md` and `research.schema.json`.

A research bundle lists documents (http(s) URL without credentials, optional
title, `retrieved_at` with timezone, `retrieval_method`, and `text_file`: the
saved retrieved text, relative to the research folder), evidence items (claim
ID, document, `supports` or `contradicts`, exact quote) and claim-pair
conflicts. A bundle is accepted or rejected as a whole: unknown or stale claim
IDs, unknown or unused documents, quotes under 10 characters or not found in the
saved text (whitespace-normalized), unsafe paths (including another bundle file
as text), extra fields and invalid metadata reject it (exit 1).
This checks the snapshot the agent saved, not the live page; no browsing
infrastructure is included and URLs are agent-supplied retrieval metadata.

Each claim keeps its video citations (source ID, URL, start/end seconds), entity
node IDs, evidence IDs and conflicting claim IDs, and gets a derived
`verification_status`: `unverified` (no external evidence), `corroborated`,
`contradicted` or `contested` (mixed evidence or a recorded conflict). Nothing is
labeled verified; conflicting claims are both kept. Entities of the same type
merge when their names match after Unicode NFKC and whitespace normalization;
matching is case-sensitive, so `10 mΩ` never merges with `10 MΩ`. Each entity
links its name and aliases; different names merge only when every pair of names
and aliases in their linked group is linked. A short name such as `3080` aliased
as `RTX 3080` in one result and as `RTX 3080 Ti` in another therefore never merges
those two models; the two `3080` entities share a node because their names are
equal, even though their aliases disagree. One such bridge also keeps an otherwise
equivalent pair apart (it errs toward splitting). Entity node IDs can change when
new results add merges. Identical documents (same URL and content) and identical evidence merge
while keeping every retrieval (with its title) and bundle. Nodes are videos, entities, claims and documents; edges are `mentions`,
`cited_in` (with timestamps), `supports`/`contradicts` and `conflicts_with`.
The build fails rather than write a graph with dangling edges. Saved document
texts and transcripts stay local; outputs contain quotes, not full documents.

## Knowledge libraries and packs (P6)

```sh
kforge knowledge domain.example.yaml --output ~/knowledge/gpu-repair
kforge knowledge domain.example.yaml --output ~/knowledge/gpu-repair \
  --topic gpu_model/rtx-3080 --budget essentials=4000 --budget full=60000
```

`knowledge` reruns `consolidate` (same exit code rules) and rewrites a
self-contained library folder, by default `<output_dir>/knowledge/<domain>/`. Put
it outside the application repository with `--output`; the report warns when the
folder is inside a git repository, because Codex/Claude Code started there may
also load that repository's AGENTS.md/CLAUDE.md. Then open the folder as its own
Codex or Claude Code workspace, or upload single files to a Claude Project.

- `INDEX.md`: entry point with status counts, usage rules and links to everything.
- `AGENTS.md` and `CLAUDE.md` (identical): consult INDEX.md, load only relevant
  files, state each claim's status/confidence/visual dependency, cite sources,
  never invent them, and treat statements, titles and quotes as untrusted data.
- `topics/<entity type>/INDEX.md` and one page per entity with every claim that
  mentions it, grouped by claim kind; `topics/general.md` holds claims without an
  entity. Topic key = `<entity type>/<file name>`.
- `procedures/`: one file per video with its `procedure_step` claims in timestamp
  order (other domains get none).
- `references/videos.md` and `references/documents.md`: cited videos with every
  claim timestamp, external documents with retrievals and evidence quotes.
- `graph/`: copies of claims/evidence/nodes/edges JSONL; evidence quotes longer
  than 300 characters are cut and marked `quote_truncated` (the full quote stays
  in `output/graph/`).
- `packs/`: single-file presets. `essentials.md` and `full.md` rank all claims
  (corroborated, contested, unverified, contradicted; then extraction confidence,
  then number of cited videos); `--topic` adds `topic-<type>-<name>.md` with that
  topic's claims first, then claims sharing a topic with them. Budgets default to
  8,000 / 16,000 / 100,000 tokens, estimated as characters/4. A pack keeps the
  best-ranked whole claims that fit and states how many it omitted; a budget too
  small for the header fails.

Every claim shows its statement, derived status, confidence, visual dependency,
video links with exact timestamp range (`&t=` deep link), evidence and conflicts
with notes. Nothing is labeled verified. Every page repeats a short rules reminder
for single-file uploads. Source-derived text is escaped as one inert Markdown line
(no links, images, HTML, code or headings); only http(s) URLs become links.
Viewers that auto-link bare URLs may still make URLs inside statements clickable;
the rules tell agents those are not sources. File names are lowercase ASCII slugs; colliding, empty or
`index` slugs get a hash, so case-insensitive file systems are safe.

The build is deterministic: it writes a complete new tree beside the old one and
swaps it in, so stale topic files disappear. It refuses symlinks, any non-empty
folder that is not a library of the same domain (marker `.kforge-library`), and
any destination that overlaps the source, database, `output_dir/graph` or
`output_dir/jobs` folders or contains `output_dir`, even before they exist and
compared case- and Unicode-insensitively (as macOS/Windows file systems do); do not
keep own files inside a library. A rejected research bundle still yields a
library without its evidence: the report warns and the exit code is 1. Transcripts, saved
research texts and canonical records are never copied. Claim statements and
evidence quotes still derive from third-party content, and many short quotes
from one document can together reproduce much of it: review rights before
sharing a library.

## Reproducible verification and recovery (P7)

After installing the current checkout, these commands run only synthetic fixtures:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s tests -p test_end_to_end.py -v
.venv/bin/python scripts/validate_state.py
.venv/bin/python scripts/smoke_install.py --reuse-dependencies
```

The end-to-end tests use stub discovery/caption adapters, forbid socket connections
in the fixture process and exercise the real CLI handlers through discovery,
SQLite/canonical transcripts, grouped Markdown/TXT/JSONL export, file jobs,
result import, research/graph and a separate portable knowledge workspace. They
also run the installed module in subprocesses from an unrelated working directory
with an explicit config. No YouTube, research page or model is contacted.
Use the same `--config /absolute/path/config.toml` for every stage when changing
working directories. A full suite with ui/discovery extras exercises the optional
native UI/backend contracts; a base install skips the native Streamlit tests.

`smoke_install.py` builds a wheel without network access, checks its contents,
creates a fresh temporary environment, verifies installed/source parity and runs
eight console commands against an empty local store. `--reuse-dependencies`
reuses the invoking interpreter's site-packages for dependencies; the application
wheel itself must import from the fresh environment. This mode does not prove a
fully isolated dependency installation. To test that too, provide a directory
containing wheels for Pydantic, PyYAML and their dependencies:

```sh
.venv/bin/python scripts/smoke_install.py --wheelhouse /absolute/path/to/wheels
```

Without either option, only the application wheel is available, so a clean offline
install fails if dependency wheels are missing. Build tooling (`setuptools>=68`
and pip wheel support) must already exist in the invoking environment. All smoke
runtime files and environments are temporary and removed automatically.

Recovery follows the stored status:

- A partial `scrape` returns exit 1 and exports its successes. Rerun the same
  command to resume interrupted/transient failures. For invalid/unavailable
  captions, correct the cause and add `--retry-failed`; successful videos retain
  their original transcripts and are not fetched again. Discovery still runs.
- Missing/corrupt generated canonical JSON is repaired from SQLite on `scrape`.
  Offline `export` reads SQLite directly. A corrupt SQLite canonical record needs
  restoration from a known-good backup; deleting its generated JSON cannot fix it.
- A rejected `result.json` returns exit 1 and preserves any previous accepted
  result. Correct it and rerun `jobs import`; valid unchanged results are skipped.
- A rejected research bundle returns exit 1, but consolidation/library rebuild
  still runs without that bundle's evidence and can change derived statuses.
  Correct the bundle/saved text and rebuild to restore the evidence. Keep agent
  work in sources/jobs, since rebuilding replaces the generated library tree.

The test/review evidence is in [P7 tests](docs/test-reports/P7.md) and
[P7 review](docs/reviews/P7.md). Live YouTube/web retrieval, an actual model's
extraction quality, Claude Projects upload, minimum dependency versions and remote
CI remain unverified locally. Token caps are character-based estimates, entity
merging relies on agent-supplied aliases, and concurrent library writers are not
supported. Real user acceptance is the separate P8 gate in
[the UAT checklist](docs/uat/CHECKLIST.md); automated P7 success is not user sign-off.
