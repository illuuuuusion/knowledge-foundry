# P7 verification and recovery

`tests/test_end_to_end.py` is self-contained: original synthetic JSON3 captions,
duplicate playlist entries, metadata/caption stubs, a small trusted domain,
hand-authored agent results and a synthetic research snapshot (example.org URL,
never fetched). It exercises real CLI handlers, not mocked workflow functions.
No model invocation or human UAT occurs. The fixture process forbids socket
connections. Subprocess CLI checks use only stored local data and remove
PYTHONPATH/PYTHONHOME; they run outside the repository using an explicit config.

Five scenarios cover the complete pipeline; corrupt caption retry/projection
repair; corrupt/invalid agent results and research recovery; interrupted batch
resume through the final library; installed module commands and redacted backend
errors. Grouping is a view: JSONL envelopes equal the SQLite snapshot, re-export
does not change it, and canonical storage remains one record per video. Job
inputs retain source text/timestamps, while TASK.md excludes source instructions.
Libraries preserve citation identity, offsets, status and visual dependency;
local links work after relocation. Raw caption texts, unquoted saved research,
local runtime paths and a synthetic environment secret are absent from the pack.

`scripts/smoke_install.py` builds a wheel, checks allowed package paths, creates a
temporary venv and runs eight console commands with a fresh empty store. It
checks every installed Python file against src and rejects an import outside
that venv. It never retrieves dependencies online. Full dependency isolation
needs `--wheelhouse`; `--reuse-dependencies` instead adds the invoking interpreter's
purelib/platlib paths via a .pth file. In reuse mode `--ignore-installed --no-deps`
is necessary so pip installs the application into the new venv without accepting
or uninstalling the parent's copy. No persistent environment is changed.

The observed clean offline attempt failed because dependency wheels were absent.
The reuse mode passed; this is application packaging/entry-point validation,
not evidence of a fully isolated dependency installation. Exact commands and
results, including initial test/script mistakes, are in docs/test-reports/P7.md.

Recovery traps: permanent invalid captions require --retry-failed, interrupted
jobs resume automatically, JSON projections repair from SQLite, invalid result
replacement preserves the accepted SQLite row, and rejected research bundles
still cause the graph/library to rebuild without their evidence (exit 1 plus a
warning). Correcting and rebuilding restores deterministic library bytes.
Corrupt authoritative SQLite payloads require a known-good backup, not projection
deletion. Generated library folders must not hold manually edited agent work.

Residual limits remain those of earlier phases: no live source/web retrieval,
actual model extraction/Claude Projects upload, Python 3.11/minimum dependencies,
Windows or remote CI validation in this environment; approximate token budgets,
agent-dependent alias quality and single-writer library builds. The P8 checklist
requires explicit user sign-off; P7 never records that sign-off.
