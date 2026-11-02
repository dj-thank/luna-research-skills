"""Exercise the actual copyable planning examples through each shipped checker."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".agents" / "skills"


class DocumentedLedgerTests(unittest.TestCase):
    def test_project_example_plans_candidate_before_review_and_final_verification(self) -> None:
        document = SKILLS / "run-diverse-luna-project/references/project-ledger.md"
        blocks = re.findall(r"```json\s*\n(.*?)\n```", document.read_text(encoding="utf-8"), re.DOTALL)
        ledger = next(item for item in map(json.loads, blocks) if item.get("ledger_type") == "project")
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "project.json"
            original = json.dumps(ledger).encode("utf-8")
            fixture.write_bytes(original)
            for package in ("project", "research"):
                with self.subTest(package=package):
                    planner = SKILLS / f"run-diverse-luna-{package}/scripts/plan_swarm.py"
                    result = subprocess.run(
                        [sys.executable, str(planner), "--ledger-json", str(fixture),
                         "--open-children", "0", "--now", ledger["assignments"][0]["planned_at"]],
                        cwd=temp, capture_output=True, text=True, encoding="utf-8", timeout=20,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    plan = json.loads(result.stdout)
                    self.assertTrue(plan["advisory_only"])
                    self.assertEqual(plan["selected_attempt_ids"], ["P-01"])
                    self.assertEqual({row["attempt_id"] for row in plan["blocked"]}, {"P-02", "P-03"})
                    self.assertEqual(fixture.read_bytes(), original)

    def test_planning_examples_validate_without_invented_spawn_receipts(self) -> None:
        examples = []
        for name, reference in (
            ("project", "project-ledger.md"),
            ("research", "research-packet.md"),
        ):
            document = SKILLS / f"run-diverse-luna-{name}" / "references" / reference
            blocks = re.findall(r"```json\s*\n(.*?)\n```", document.read_text(encoding="utf-8"), re.DOTALL)
            ledgers = [json.loads(block) for block in blocks]
            ledgers = [item for item in ledgers if isinstance(item, dict) and item.get("ledger_type") == name]
            self.assertEqual(len(ledgers), 1, f"one copyable {name} planning ledger")
            ledger = ledgers[0]
            for row in ledger["assignments"]:
                self.assertEqual(row["execution_status"], "planned")
                self.assertIsNone(row["delegated_by"]["parent_call_id"])
                self.assertIsNone(row["root_parent_call_id"])
            examples.append((name, ledger))

        for package in ("project", "research"):
            path = SKILLS / f"run-diverse-luna-{package}" / "scripts" / "check_setup.py"
            spec = importlib.util.spec_from_file_location(f"documented_{package}", path)
            checker = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(checker)
            for name, ledger in examples:
                with self.subTest(package=package, example=name), tempfile.TemporaryDirectory() as temp:
                    fixture = Path(temp) / "ledger.json"
                    fixture.write_text(json.dumps(ledger), encoding="utf-8")
                    with contextlib.redirect_stdout(io.StringIO()):
                        errors, _ = checker.validate_assignment_ledger(fixture, configured_cap=6)
                    self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
