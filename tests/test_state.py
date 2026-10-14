import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.validate_state import PHASES, RULES, validate_state


ROOT = Path(__file__).resolve().parents[1]


def initial_state():
    """Synthetic baseline, independent of the mutable repository state."""
    return {
        "schema_version": 1, "project": "knowledge-foundry", "current_phase": "P0",
        "user_testing_allowed": False, "rules": dict(RULES),
        "phases": {key: {
            "title": f"Phase {key}", "status": "pending",
            "tests": {"status": "pending", "report": None},
            "review": {"status": "pending", "report": None},
            "knowledge_updated": False, "planned_commit_message": "chore: test fixture",
            "blockers": [],
        } for key in PHASES},
    }


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = initial_state()

    def complete(self, key):
        phase = self.state["phases"][key]
        phase["status"] = "completed"
        phase["knowledge_updated"] = True
        for gate, directory, status in (
            ("tests", "test-reports", "passed"), ("review", "reviews", "approved")
        ):
            path = self.root / f"docs/{directory}/{key}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic gate evidence for validator fixture.\n")
            phase[gate] = {"status": status, "report": str(path.relative_to(self.root))}

    def test_valid_initial_and_in_progress_state(self):
        self.assertEqual(validate_state(self.state, self.root), [])
        self.state["phases"]["P0"]["status"] = "in_progress"
        self.assertEqual(validate_state(self.state, self.root), [])

    def test_valid_completion_and_next_phase(self):
        self.complete("P0")
        self.state["current_phase"] = "P1"
        self.assertEqual(validate_state(self.state, self.root), [])

    def test_p8_is_the_first_allowed_user_testing_phase(self):
        for key in PHASES[:-1]:
            self.complete(key)
        self.state.update(current_phase="P8", user_testing_allowed=True)
        self.assertEqual(validate_state(self.state, self.root), [])
        self.complete("P8")
        self.state["current_phase"] = "DONE"
        self.assertEqual(validate_state(self.state, self.root), [])

    def test_rejects_malformed_structure_and_wrong_rules(self):
        variants = [None, [], {"schema_version": 1}]
        for field, value in (("schema_version", True), ("project", "wrong"),
                             ("rules", {}), ("phases", {})):
            state = copy.deepcopy(self.state)
            state[field] = value
            variants.append(state)
        state = copy.deepcopy(self.state)
        state["phases"]["P0"] = None
        variants.append(state)
        for state in variants:
            with self.subTest(state=state):
                self.assertTrue(validate_state(state, self.root))

    def test_rejects_early_uat_and_wrong_current_phase(self):
        self.state["user_testing_allowed"] = True
        self.assertTrue(validate_state(self.state, self.root))
        self.state["user_testing_allowed"] = False
        self.state["current_phase"] = "P2"
        self.assertTrue(validate_state(self.state, self.root))

    def test_rejects_work_ahead(self):
        self.state["phases"]["P1"]["status"] = "in_progress"
        self.assertTrue(validate_state(self.state, self.root))
        self.complete("P1")
        self.assertTrue(validate_state(self.state, self.root))

    def test_completed_requires_every_gate_and_no_blockers(self):
        self.complete("P0")
        self.state["current_phase"] = "P1"
        for field, value in (("tests", {"status": "pending", "report": None}),
                             ("review", {"status": "pending", "report": None}),
                             ("knowledge_updated", False), ("blockers", ["blocked"])):
            state = copy.deepcopy(self.state)
            state["phases"]["P0"][field] = value
            with self.subTest(field=field):
                self.assertTrue(validate_state(state, self.root))

    def test_rejects_missing_empty_and_unsafe_reports(self):
        self.complete("P0")
        self.state["current_phase"] = "P1"
        report = self.root / "docs/reviews/P0.md"
        report.unlink()
        self.assertTrue(validate_state(self.state, self.root))
        report.write_text(" ")
        self.assertTrue(validate_state(self.state, self.root))
        self.state["phases"]["P0"]["review"]["report"] = "../../outside.md"
        self.assertTrue(validate_state(self.state, self.root))

    def test_rejects_report_symlink_outside_repository(self):
        self.complete("P0")
        self.state["current_phase"] = "P1"
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "report.md"
            external.write_text("outside fixture")
            report = self.root / "docs/reviews/P0.md"
            report.unlink()
            report.symlink_to(external)
            self.assertTrue(validate_state(self.state, self.root))

    def test_blocked_requires_a_documented_blocker(self):
        phase = self.state["phases"]["P0"]
        phase["status"] = "blocked"
        self.assertTrue(validate_state(self.state, self.root))
        phase["blockers"] = ["Installation unavailable"]
        self.assertEqual(validate_state(self.state, self.root), [])

    def test_rejects_invalid_gate_types_and_statuses(self):
        phase = self.state["phases"]["P0"]
        phase["status"] = "in_progress"
        for gate in (None, [], {"status": "unknown", "report": None},
                     {"status": [], "report": None},
                     {"status": "passed", "report": None}):
            state = copy.deepcopy(self.state)
            state["phases"]["P0"]["tests"] = gate
            with self.subTest(gate=gate):
                self.assertTrue(validate_state(state, self.root))

    def test_rejects_non_string_phase_status_without_crashing(self):
        self.state["phases"]["P0"]["status"] = []
        self.assertTrue(validate_state(self.state, self.root))

    def test_pending_cannot_record_finished_work(self):
        self.state["phases"]["P1"]["knowledge_updated"] = True
        self.assertTrue(validate_state(self.state, self.root))

    def test_rejects_multiline_commit_and_coauthor_trailers(self):
        for subject in ("not conventional", "chore: initialize\nCo-authored-by: X",
                        "chore: größe", "chore: initialize\n"):
            self.state["phases"]["P0"]["planned_commit_message"] = subject
            with self.subTest(subject=subject):
                self.assertTrue(validate_state(self.state, self.root))

    def test_cli_positive_and_negative_exit_codes(self):
        path = self.root / "state.json"
        for content, expected in ((json.dumps(self.state), 0), ("{broken", 1),
                                  ("[]", 1)):
            path.write_text(content)
            result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_state.py"),
                                     str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_actual_repository_state(self):
        self.assertEqual(validate_state(json.loads((ROOT / "state.json").read_text()), ROOT), [])
