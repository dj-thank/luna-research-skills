"""Replay saved real-task handoffs; this CI test does not clone upstream."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

import read_evidence as E
import read_requirements as R

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples/value_chain_task"
read = lambda p: json.loads(p.read_bytes())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

class ExternalTaskExample(unittest.TestCase):
    def test_frozen_obligations_and_all_saved_test_outcomes(self):
        contract = read(EXAMPLE / "contract.json")
        report = read(EXAMPLE / "results.json")
        self.assertEqual(digest(EXAMPLE / "probe.py"), report["probe_sha256"])
        self.assertEqual(digest(EXAMPLE / "contract.json"), report["contract_sha256"])
        names = sorted(node.name for node in ast.walk(ast.parse(
            (EXAMPLE / "probe.py").read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"))
        self.assertEqual(names, sorted(contract["fail_to_pass"] + contract["pass_to_pass"]))
        self.assertEqual(len(names), 12)
        self.assertEqual(set(report["variants"]), set(contract["variants"]))
        for name, variant in report["variants"].items():
            with self.subTest(variant=name):
                self.assertEqual(sorted(row["id"] for row in variant["tests"]), names)
                for metric, key in (("fix_pass", "fail_to_pass"), ("preserve_pass", "pass_to_pass")):
                    passed = sum(row["status"] == "PASS" for row in variant["tests"] if row["id"] in contract[key])
                    self.assertEqual(passed, contract["expected"][name][metric])
        self.assertEqual(report["variants"]["classify-then-consume"]["full_suite"]["tests"], 905)
        self.assertEqual(report["variants"]["classify-then-consume"]["full_suite"]["exit_code"], 0)

    def test_copyable_commands_preserve_facts_and_reject_regression(self):
        doc = (ROOT / "docs/external-task-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 3)
        for index, (line, code) in enumerate(zip(commands, (0, 1, 0))):
            with self.subTest(command=index):
                args = shlex.split(line)
                args[0] = sys.executable
                run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
                self.assertEqual(run.returncode, code, run.stdout + run.stderr)
                result = json.loads(run.stdout)
                if code:
                    self.assertEqual(result["relation_gaps"], [{"id":"existing-behavior", "reason":"MISMATCH"}])
                    self.assertNotIn("requirements", result)
                else:
                    source = read(ROOT / args[args.index("--source") + 1])
                    self.assertEqual([o for row in result["requirements"] for o in row["observations"]], source["observations"])
                    if index == 0:
                        receipt = source["observations"][1]["value"]
                        self.assertEqual(len(receipt["nonpassing"]), 2)

    def test_corrupted_receipts_do_not_complete_the_task(self):
        original = read(EXAMPLE / "fixed-source.json")
        for control in ("stale", "missing", "skipped"):
            with self.subTest(control=control), tempfile.TemporaryDirectory() as tmp:
                source = copy.deepcopy(original)
                receipt = source["observations"][1]["value"]
                if control == "stale":
                    receipt["source_sha256"] = read(EXAMPLE / "regression-source.json")["observations"][1]["value"]["source_sha256"]
                else:
                    receipt["passed_ids"].remove("test_preserve_scalars")
                    if control == "skipped":
                        receipt["nonpassing"].append({"id":"test_preserve_scalars", "status":"SKIP"})
                folder = Path(tmp)
                (folder / "source.json").write_bytes(E.encode(source))
                question = read(EXAMPLE / "fixed-complete.json")
                question["source_sha256"] = digest(folder / "source.json")
                (folder / "question.json").write_bytes(E.encode(question))
                result = R.read_requirements(folder / "question.json", digest(folder / "question.json"), folder / "source.json")
                self.assertEqual(result["status"], "INSUFFICIENT")
                self.assertNotIn("requirements", result)
                expected = "source-revision" if control == "stale" else "existing-behavior"
                self.assertIn({"id":expected, "reason":"MISMATCH"}, result["relation_gaps"])

if __name__ == "__main__":
    unittest.main()
