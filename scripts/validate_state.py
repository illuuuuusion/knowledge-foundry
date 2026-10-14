"""Check phase order and recorded gates, without claiming to execute those gates."""

import argparse
import json
from pathlib import Path
import re
import sys


PHASES = tuple(f"P{index}" for index in range(9))
RULES = {
    "agent_written_tests_required": True,
    "independent_ai_review_preferred": True,
    "review_after_each_phase": True,
    "commits_english_only": True,
    "co_author_trailers_forbidden": True,
    "mcp_required": False,
}


def validate_state(state: object, root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state must be an object"]
    if type(state.get("schema_version")) is not int or state["schema_version"] != 1:
        errors.append("schema_version must be 1")
    if state.get("project") != "knowledge-foundry":
        errors.append("project must be knowledge-foundry")
    rules = state.get("rules")
    if not isinstance(rules, dict) or set(rules) != set(RULES) or any(
        rules.get(key) is not value for key, value in RULES.items()
    ):
        errors.append("rules must preserve the workflow contract")
    phases = state.get("phases")
    if not isinstance(phases, dict) or set(phases) != set(PHASES):
        return errors + ["phases must contain exactly P0 through P8"]
    first_incomplete = next(
        (key for key in PHASES if not isinstance(phases[key], dict)
         or phases[key].get("status") != "completed"), "DONE"
    )
    if state.get("current_phase") != first_incomplete:
        errors.append("current_phase must be the first incomplete phase or DONE")
    uat_ready = all(
        isinstance(phases[key], dict) and phases[key].get("status") == "completed"
        for key in PHASES[:-1]
    )
    if state.get("user_testing_allowed") is not uat_ready:
        errors.append("user_testing_allowed must match completion of P0–P7")
    seen_incomplete = False
    for key in PHASES:
        phase = phases[key]
        if not isinstance(phase, dict):
            errors.append(f"{key}: phase must be an object")
            seen_incomplete = True
            continue
        status = phase.get("status")
        later = seen_incomplete
        if status != "completed":
            seen_incomplete = True
        if not isinstance(status, str) or status not in {
            "pending", "in_progress", "blocked", "completed"
        }:
            errors.append(f"{key}: invalid phase status")
        if later and status != "pending":
            errors.append(f"{key}: cannot work ahead of an incomplete phase")
        if not isinstance(phase.get("title"), str) or not phase["title"].strip():
            errors.append(f"{key}: missing title")
        commit = phase.get("planned_commit_message")
        if not isinstance(commit, str) or not re.fullmatch(
            r"(?:chore|feat|fix|test|docs|refactor|build|ci|perf|style)"
            r"(?:\([a-z0-9_-]+\))?: [A-Za-z][A-Za-z0-9 ,./()_-]*", commit
        ):
            errors.append(f"{key}: expected single-line English Conventional Commit")
        blockers = phase.get("blockers")
        if not isinstance(blockers, list) or any(
            not isinstance(item, str) or not item.strip() for item in blockers
        ):
            errors.append(f"{key}: blockers must be a list of nonempty strings")
        if status == "blocked" and not blockers:
            errors.append(f"{key}: blocked phase needs a documented blocker")
        if type(phase.get("knowledge_updated")) is not bool:
            errors.append(f"{key}: knowledge_updated must be boolean")
        gates = {}
        for gate, allowed, directory in (
            ("tests", {"pending", "passed", "failed"}, "test-reports"),
            ("review", {"pending", "approved", "changes_requested"}, "reviews"),
        ):
            value = phase.get(gate)
            if not isinstance(value, dict):
                errors.append(f"{key}: {gate} must be an object")
                continue
            gates[gate] = value.get("status")
            if not isinstance(value.get("status"), str) or value["status"] not in allowed:
                errors.append(f"{key}: invalid {gate} status")
            report = value.get("report")
            if report is not None:
                expected = f"docs/{directory}/{key}.md"
                if report != expected:
                    errors.append(f"{key}: {gate} report must be {expected}")
                else:
                    path = root / expected
                    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                        errors.append(f"{key}: {gate} report missing or outside repository")
                    elif not path.read_text(encoding="utf-8").strip():
                        errors.append(f"{key}: {gate} report is empty")
            if value.get("status") != "pending" and report is None:
                errors.append(f"{key}: {gate} result requires a report")
        if gates.get("review") == "approved" and gates.get("tests") != "passed":
            errors.append(f"{key}: review approval requires passing tests")
        if status == "pending" and (
            any(value != "pending" for value in gates.values())
            or phase.get("knowledge_updated") is True
            or any(isinstance(phase.get(gate), dict)
                   and phase[gate].get("report") is not None for gate in ("tests", "review"))
        ):
            errors.append(f"{key}: pending phase cannot record finished work")
        if status == "completed" and (
            gates.get("tests") != "passed" or gates.get("review") != "approved"
            or phase.get("knowledge_updated") is not True or blockers != []
        ):
            errors.append(f"{key}: completed phase requires all gates and no blockers")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "state.json")
    args = parser.parse_args(argv)
    try:
        state = json.loads(args.state.read_text(encoding="utf-8"))
        errors = validate_state(state, args.state.resolve().parent)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"State validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("State validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
