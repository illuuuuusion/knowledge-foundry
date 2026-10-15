# P5 evidence consolidation and graph

## Contract

`builder/graph.py`: Pydantic research bundle models, `read_bundle`,
`merge_entities`, `check_graph` and `consolidate`; CLI `kforge consolidate
<domain.yaml>`. No SQLite migration: outputs are a pure, deterministic function of
current extraction results (P4 table) plus bundle files, rewritten on every run.

Current results = `extraction_results` rows of the domain whose job ID is in
`plan(read_snapshot(db), domain)`. Claim ID = `claim:<job id>:<local claim id>`.
Bundles live in `<source_dir>/research/<domain>/*.json` (top level, sorted);
document texts may be in subfolders. Agents learn the format from RESEARCH.md and
research.schema.json written next to claims.jsonl.

## Rules

- Whole-bundle accept/reject. Quotes need at least 10 characters and must occur in
  the saved text after whitespace collapse; every document must be used by
  evidence; text files must resolve inside the research folder, not be symlinks
  or top-level bundle `.json` files, be UTF-8 and at most 10 MiB; unreadable paths
  (NUL, OS errors) reject the bundle instead of aborting the run. URLs: http(s), host, no credentials/whitespace.
  `retrieved_at` must carry a timezone. Extra fields (e.g. a status) are rejected.
- Status is derived, never supplied: conflicts or supports+contradicts ->
  contested; contradicts -> contradicted; supports -> corroborated; else
  unverified. There is no `verified` value; transcript observations never become
  verified facts. Multiple videos agreeing does not change the status.
- Entity merge: same type and equal NFKC/whitespace-normalized name (case-
  sensitive: unit prefixes such as m/M differ). Each entity links all its strings
  (name + aliases) pairwise; a linked group of strings, including alias-only
  strings, merges its names only if every pair is linked (complete graph). A
  bridge such as `3080` -> `RTX 3080` / `RTX 3080 Ti` spread over several entities
  looks like a true alias, so such groups stay split by name (review B1/B2/B3).
  One entity listing both models as its own aliases does merge them (review N9):
  that is an explicit agent statement, indistinguishable from a benign alias star.
  Equal names still merge although their aliases disagree; one bad bridge keeps a
  genuine pair apart. An agent-made complete triangle does merge, by design. Node ID hashes the
  smallest merged key and may change when new results add merges; label = most
  frequent normalized name, ties lexicographic.
- Documents dedupe by URL + content SHA-256 (all retrievals with titles kept);
  conflict edges list notes and asserting bundles; evidence by
  claim, document, stance and normalized quote (all bundles kept). Claims are not
  deduplicated across jobs (ponytail: paraphrases rarely match exactly).
- `check_graph` refuses duplicate node IDs and dangling edges before any write.
  The graph folder must not be a symlink; files are atomic, the set is not.

## Pitfalls

- Bundles must be rewritten when their claims become stale (domain settings or
  transcript changed): they are rejected as unknown/stale, not partially applied.
- A quote check proves consistency with the agent's saved snapshot only.
- Evidence output embeds document metadata; full document text stays in sources.
- Merge cost is quadratic in aliases per entity (review N10: 1,500 aliases ~2.4 s,
  3,000 ~12.7 s). P4 does not cap aliases; cap them if real results get that large.
