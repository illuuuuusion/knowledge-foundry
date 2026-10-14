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
