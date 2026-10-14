# P0 architecture

`src/kforge` is an installable Python >=3.11 package with a standard-library-only
runtime. `kforge` and `python -m kforge` use the same argparse entry point.
The only foundation commands are `config` and `init`; help and imports have no
storage effects. `ingest`, `export`, `builder` and `knowledge` are empty module
boundaries for later phases, not implementations of those phases.

## Configuration

Immutable Config values come from environment > explicit TOML > defaults.
Supported names are documented in `.env.example` and `config.example.toml`.
No dotenv parser is used, and arbitrary environment variables are not displayed.
TOML paths are relative to the configuration directory; environment paths use
the working directory. Database defaults follow the resolved data directory.
Invalid sections, keys, types, log levels and unreadable files fail explicitly.
Logging goes to stderr using Python logging; no source text is logged in P0.

## SQLite strategy

`storage.migrate` applies ordered versions under BEGIN IMMEDIATE, records
schema_migrations and PRAGMA user_version, then commits together. Failure rolls
back DDL, history and version. Repeated init skips completed migrations, and
newer database versions are rejected. P0 creates only migration history; domain
tables and resumable ingestion belong to P2. Append migrations, never rewrite
an applied version. Each migration is individual SQL statements, not executescript
(which would interfere with the surrounding transaction).

Canonical records in later phases must preserve one record per video, segment
timestamps, provenance and verification status. Grouping is only an export view.
External text is untrusted. No mandatory hosted service, MCP or proprietary API.

## Governance

The validator verifies JSON structure, rules, phase order, recorded gate status,
nonempty local report files and the P8 user-testing boundary. It does not execute
tests or infer review approval from a file. Reports cannot point outside the repo,
including through symlinks. Unit tests use independent synthetic state fixtures
so advancing state.json does not change the expected workflow tests.
