# P6 knowledge libraries and packs

## Contract

`knowledge/library.py`: `build(database, source_dir, output_dir, domain,
destination=None, topics=(), budgets=None)`; CLI `kforge knowledge <domain.yaml>
[--output DIR] [--topic TYPE/NAME ...] [--budget PRESET=TOKENS ...]`. It reruns
`graph.consolidate` and renders only from the four graph JSONL files; no SQLite
migration, no new dependency. Default destination `<output_dir>/knowledge/<domain>`.

Layout: INDEX.md, AGENTS.md = CLAUDE.md, topics/<entity type>/{INDEX.md,<slug>.md},
topics/general.md, procedures/{INDEX.md,<slug>.md}, references/{videos,documents}.md,
graph/*.jsonl (copies; quotes over 300 chars cut + `quote_truncated`), packs/{essentials,full,topic-<type>-<slug>}.md and the
marker `.kforge-library` (domain ID). INDEX.md reaches every file through links.

## Rules

- Untrusted strings (statements, labels, aliases, titles, quotes, notes, retrieval
  metadata) go through `_md`: whitespace collapsed to one line, C0/C1 controls and
  bidi overrides removed, ``\ ` * _ [ ] < > ! | ~ & #`` backslash-escaped (`#` so a
  trailing run cannot become an ATX closing sequence), and never placed at line
  start. Every page carries a one-line rules reminder linking AGENTS.md. Validated identifiers
  (claim/source IDs, kinds, entity types, statuses) appear raw in code spans. Only
  http(s) URLs become links, as `<...>` destinations with controls, space, `<>\`
  percent-encoded.
- File stems: NFKD -> ASCII -> lowercase slug, max 60 chars; colliding, empty
  ('topic') or 'index' stems get `-<sha256(key)[:8]>` (key = entity label per type or
  video ID), repeated until no plain stem clashes with a hashed one (review N1:
  crafted labels like `x-4b68ab38`); hashed stems that still clash get the full
  digest (review N9: 8 hex digits collide after ~43k tries). A case-folded path
  collision check guards every generated file.
- Packs rank by status (corroborated, contested, unverified, contradicted),
  confidence, then distinct cited videos, then ID. A pack is the longest prefix of
  whole claim blocks whose header + blocks + omission note fit `budget * 4`
  characters; too small for the header -> ValueError, nothing written.
- Topic pack = claims mentioning the entity (first), then claims mentioning any
  entity co-mentioned with it.
- Procedures = claims of kind `procedure_step` (constant), per cited video, ordered
  by first timestamp in that video.
- Writes: full tree into `.<name>.<token>.new`, rename old to `.old`, rename new in,
  delete old; restore on failure. Refuse symlinked destination, non-directories and
  non-empty folders without this domain's exact marker. Refuse (by realpath, NFC +
  casefold so `SOURCES` or NFD spellings match on macOS/Windows, review B3; even if
  missing) destinations inside/around source_dir, the database folder,
  output/graph, output/jobs, or containing output_dir (review B2: a library at
  `sources/research/<domain>` deleted the agent's bundles on rebuild).
- Read JSONL with `split('\n')`, never `splitlines()`: P5 writes U+2028/U+2029/U+0085
  raw inside JSON strings (review B1 crashed the whole build on one such title).

## Pitfalls

- Topic file names follow entity labels; merges or new colliding labels change
  them (and their hashed suffix). Keys in INDEX are per build, not permanent IDs.
- Token counts are characters/4 estimates; non-Latin text underestimates tokens.
- Relative links inside an uploaded single pack do not resolve outside the library.
- P5 quotes have no maximum length; the library cuts them to 300 characters, the
  local graph keeps them. Bounding them in P5 would need a deliberate schema bump.
- Many quotes under 300 characters can still reproduce a whole saved page (review
  N10); no per-document quote budget exists. Review before sharing.
- Rejected bundles do not stop the swap: the library loses their evidence (report
  warning, exit 1), mirroring consolidate (review N5).
- GFM/linkify viewers turn bare URLs inside escaped text into links (review N3);
  strict CommonMark does not. The rules say such URLs are not sources.
- The default destination lies inside the repo when kforge runs there (warning).
- Concurrent builds to one destination are not locked (single writer assumed).
