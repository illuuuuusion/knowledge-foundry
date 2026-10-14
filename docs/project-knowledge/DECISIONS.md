# Decision log

## 2026-10-14 — P0 foundation

- Use a src layout, setuptools and Python >=3.11. No runtime dependency is needed
  for this phase; TOML, argparse, SQLite and unittest are in the standard library.
- Keep paths explicit/configurable and initialization deliberate. Merely loading
  configuration or asking for help must not create data or output.
- Use versioned transactional SQLite migrations, without premature domain tables.
- Use unittest with offline, temporary synthetic fixtures. Test installed package
  behavior and subprocess CLI entry points, not only imports from the source tree.
- Bootstrap missing project memory, review template and future UAT checklist in
  P0. The checklist is preparation only; no human testing took place.
- GitHub origin is configured, so add CI for Python 3.11 and 3.14. Local results
  on Python 3.14 do not imply that GitHub CI or Python 3.11 was executed.
- The host provides python3 but no python command. A local .venv provides python,
  preserving the required `python scripts/validate_state.py` command on activation.
- Initial sandbox installation could not resolve PyPI. The authorized retry
  downloaded setuptools and installed the package. Test fixtures remain offline;
  first-time package builds require setuptools to be available.
- A separate AI review agent approved P0 after inspecting the actual staged diff
  and rerunning checks. No blocking issue or review-driven code change remained.
  P0 ends here; advancing the state to P1 is a handoff, not permission to implement
  discovery under START_PROMPT.md.

## 2026-10-14 — P1 source discovery

- The user explicitly authorized P1 after P0; START_PROMPT.md's initial P0 stop
  does not block this new request. Implement only discovery, no transcript retrieval.
- Use optional yt-dlp metadata extraction behind a streaming protocol; base installs
  and deterministic tests work without that backend. No required model/API service.
- Add `discover` now to make structured manifests usable; `scrape` and `export`
  remain P3 work. Extend the shared P0 CLI and rerun all 32 foundation regressions.
- Select unique videos in source order, then optionally sort by ID. Do not traverse
  a whole remote channel solely to satisfy sorting. Conservatively flag truncation
  when a collection reaches the limit; never silently claim complete coverage.
- Dedup canonical source requests/video IDs while retaining original inputs and
  every observed metadata version. Treat source metadata and descriptions as
  unverified, untrusted data; preserve conflict observations rather than overwriting.
- Classify failures conservatively and preserve partial results. Do not emit raw
  exceptions/backend logs or add credentials, automatic retries or bot workarounds.
- Inspect official yt-dlp docs/source and validate the native API locally with
  synthetic responses; this is not evidence of live YouTube availability.
- Initial independent review found dropped temporal provenance and an extreme
  numeric-field overflow. Preserve source timestamp/release/modified/epoch values
  and date fields, and safely omit malformed optional numbers. Regression tests
  must assert those fields survive duplicates and JSON, and the collection continues.
- The same separate reviewer rechecked the updated actual diff, reran all 64 tests
  and prior reproductions, and approved P1 with no unresolved findings. Advance to
  P2 for handoff only; do not implement transcript ingestion under this P1 request.

## 2026-10-14 — P2 transcript ingestion

- The user explicitly requested P2. Implement Python caption/storage services only;
  scrape/export CLI and Streamlit remain P3. Changes to shared P0 migration tests
  reflect append-only v2; all earlier regression tests must pass again.
- Reuse optional yt-dlp rather than add a mandatory API or fallback dependency.
  Select source-provided manual/auto tracks by language, then kind, exact locale and
  deterministic format rank. No arbitrary-language fallback or media download.
- Normalize JSON3, VTT and SRT offline, preserving original indices/cue/word timing
  and raw event/cue evidence. Sort stable by start/index, retain overlapping/zero
  duration cues and never clip offsets based on unverified metadata duration.
- Persist one canonical video row in SQLite, then atomically project one JSON file.
  This makes file-write interruptions recoverable without redownloading; the source
  manifest is retained separately so original URLs and source failures survive.
- A successful record is reused even if selection settings change; new discovery
  observations/manifests are merged. Explicit successful-caption replacement and
  multiple-language storage are deferred rather than duplicating canonical videos.
- Use a separate SQLite exclusive lock to serialize local workers without holding
  the state database's transaction across remote requests. Lock release on process
  exit permits resume; distributed orchestration is outside this phase.
- Keep retry budgets per invocation and lifetime attempt counts per video; classify
  errors safely and allow an explicit retry_failed flag for permanent failures.
- Reject invalid caption bounds, nonfinite values, bad UTF-8 and escaped unpaired
  Unicode surrogates before SQLite writes. Never execute caption instructions or
  label caption claims verified; request headers never enter stored provenance.
- Independent review reproduced inherited verified status from a constructed
  Video input. Force new captions unverified and test that original manifest
  evidence remains intact. Also resolve store paths so database symlink aliases
  share the same worker lock; regression checks exclusion through an alias.
- The same separate reviewer approved follow-up after independently passing
  all 104 tests, rechecking both fixes in offline reproductions/subprocesses and
  confirming installed/source parity. All P2 acceptance gates are satisfied;
  advance to P3 for handoff only and retain the P8-only UAT boundary.
