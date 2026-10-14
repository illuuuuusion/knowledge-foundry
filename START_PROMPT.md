# Initial agent prompt — copy into Codex / Claude Code

You are implementing Knowledge Foundry. Work ONLY in the current active phase recorded in `state.json`. Read `AGENTS.md`, `IMPLEMENTATION_PLAN.md`, `state.json`, and `docs/project-knowledge/INDEX.md` first; inspect other project knowledge as needed.

Start with P0. Do not implement P1 or later yet. Write and actually run automated tests for P0. Record exact results in `docs/test-reports/P0.md`, request an independent AI review of the actual diff (or use a clearly labeled review-only pass if no second agent is available) and record it in `docs/reviews/P0.md`. Fix blocking findings and rerun tests. Update project knowledge and `state.json` according to the phase gate. Run `python scripts/validate_state.py` before committing. Use the planned Conventional Commit subject in English, without any `Co-authored-by` trailers. Verify the git log message after committing.

Do not perform real human UAT until P8; AI-authored tests are required in every earlier phase. Do not claim review approval, test success, or a human result without actual evidence. If no independent reviewer is available, explicitly disclose that limitation; run a dedicated review-only pass with findings, and never falsely label it independent.

At the end, report changed files, executed commands, actual test results, review outcome, commit hash, and next phase. Stop after P0.
