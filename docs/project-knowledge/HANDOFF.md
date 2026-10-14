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
