# Knowledge Foundry

Local-first Python foundation for source-grounded video knowledge workflows.
P0 provides configuration, logging, SQLite migrations and a CLI skeleton.
Discovery, transcript ingestion and knowledge exports arrive in later phases;
they are not implemented yet. No external requests or model APIs are required.

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

See `AGENTS.md`, `state.json`, `IMPLEMENTATION_PLAN.md` and
`docs/project-knowledge/INDEX.md` for phase order and evidence gates. CI installs
the package and runs the same offline tests and state validator on Python 3.11
and 3.14. A validator checks recorded evidence and ordering; it does not run tests
or prove review quality. Human acceptance is reserved for P8.
