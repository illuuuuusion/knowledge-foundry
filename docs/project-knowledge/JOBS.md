# P4 extraction jobs

## Contract

`builder/jobs.py` holds everything: Pydantic models (`Domain`, `ExtractionResult`,
`Entity`, `Claim`, `Citation`), `load_domain` (YAML), `plan`, `create_jobs`,
`validate` and `import_results`. CLI `kforge jobs create|import <domain.yaml>`
calls them directly with Config database/output paths. No model API is called;
an agent (Claude Code/Codex) works on job folders interactively.

Domain YAML is trusted user configuration (id slug, title, guidance, entity types,
claim kinds, `max_input_chars`). Only its values, validated IDs and numbers enter
TASK.md; transcript text appears only JSON-encoded in `input.jsonl`.

`plan` reads `read_snapshot` (read-only, validated canonical records) and
partitions each video separately in segment order by a character budget; a single
oversize segment gets its own job. Per-video partitioning keeps existing job IDs
stable when videos are added. Job ID = `<video id>-<part:04d>-<sha256[:12]>` over
input lines, domain settings and `RESULT_SCHEMA_VERSION`. Bump that constant when
the result schema, TASK.md rules or validation change, otherwise old results stay
`unchanged` without revalidation. Folders: `output_dir/jobs/<domain>/<job id>/`.

## Validation and import

The importer recomputes jobs from SQLite and never trusts the job folder's input
files. A result is accepted or rejected as a whole: strict Pydantic JSON schema
(no coercion, no extra keys, finite non-negative times, end >= start, at least one
citation, `verification_status` literally `unverified`), then cross-references:
job ID, unique IDs, domain kinds/entity types, entity references both ways,
citation source in the job and start/end within the job span and overlapping a
segment. Errors list locations and fixed messages, never submitted values; an
unknown key appears in its location, truncated to 200 characters.

Migration v3 appends `extraction_results` (job_id PK, domain, source_id,
result_sha256, payload with domain settings, input/result hashes and normalized
result). Same hash -> `unchanged`; invalid replacement -> `rejected` and the earlier
row stays; valid replacement -> upsert. Pending is derived from missing
result.json. Symlinked/oversized (>10 MiB) results are rejected, symlinked job
folders refused by create and reported stale by import.

## Pitfalls

- Pydantic JSON accepts duplicate keys (last wins); stored payload is the model dump.
- Citation check is span + overlap, so a range touching a segment edge may cover a gap.
- Rows from older job IDs (changed settings or replaced transcripts) stay in SQLite.
  P5 must use only results whose job ID is in the current `plan`.
- v2 stores need `kforge init` before export/jobs; the error message says so.
- `jobs create` on an empty store writes no folder, so a following `import` fails
  with "run kforge jobs create"; the real cause is that no transcripts are stored.
