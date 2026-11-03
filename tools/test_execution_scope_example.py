"""Check saved task evidence and scope guards without fetching upstream code."""
import ast
import copy
import hashlib
import importlib.util
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
EXAMPLE = ROOT / "examples/iequals_task"
read = lambda p: json.loads(p.read_bytes())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


class ExecutionScopeExample(unittest.TestCase):
    def test_frozen_tests_and_saved_dependency_counterexample(self):
        contract = read(EXAMPLE / "contract.json")
        report = read(EXAMPLE / "results.json")
        self.assertEqual(digest(EXAMPLE / "probe.py"), report["probe_sha256"])
        self.assertEqual(digest(EXAMPLE / "contract.json"), report["contract_sha256"])
        names = sorted(node.name for node in ast.walk(ast.parse(
            (EXAMPLE / "probe.py").read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"))
        self.assertEqual(names, sorted(contract["fail_to_pass"] + contract["pass_to_pass"]))
        self.assertEqual(len(names), 12)
        self.assertEqual(set(report["variants"]), set(contract["expected"]))
        for name, variant in report["variants"].items():
            with self.subTest(variant=name):
                self.assertEqual(sorted(row["id"] for row in variant["tests"]), names)
                self.assertEqual(sorted(variant["code_scope"]), sorted(contract["code_scope"]))
                self.assertEqual(sorted(variant["module_origins"].values()), sorted(contract["code_scope"]))
                for metric, key in (("fix_pass", "fail_to_pass"), ("preserve_pass", "pass_to_pass")):
                    passed = sum(row["status"] == "PASS" for row in variant["tests"] if row["id"] in contract[key])
                    self.assertEqual(passed, contract["expected"][name][metric])
        fixed = report["variants"]["fixed"]
        changed = report["variants"]["changed-helper-control"]
        self.assertEqual(fixed["primary_sha256"], changed["primary_sha256"])
        self.assertNotEqual(fixed["code_scope"]["more_itertools/recipes.py"], changed["code_scope"]["more_itertools/recipes.py"])
        self.assertEqual(report["fixed_full_suite"]["tests"], 905)
        self.assertEqual(report["fixed_full_suite"]["exit_code"], 0)

    def test_documented_commands_reject_replayed_receipt_and_preserve_valid_facts(self):
        doc = (ROOT / "docs/execution-scope-evaluation.md").read_text(encoding="utf-8")
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
                    self.assertEqual(result["relation_gaps"], [{"id": "package-code", "reason": "MISMATCH"}])
                    self.assertNotIn("requirements", result)
                else:
                    source = read(ROOT / args[args.index("--source") + 1])
                    self.assertEqual([o for row in result["requirements"] for o in row["observations"]], source["observations"])
                    if index == 0:
                        proposal, receipt = [row["value"] for row in source["observations"][:2]]
                        self.assertEqual(proposal["primary_sha256"], receipt["primary_sha256"])
                        self.assertNotEqual(proposal["code_scope"], receipt["code_scope"])

    def test_scope_capture_rejects_unreviewed_inventory_and_cached_code(self):
        spec = importlib.util.spec_from_file_location("iequals_scope_probe", EXAMPLE / "probe.py")
        probe = importlib.util.module_from_spec(spec)
        previous = sys.dont_write_bytecode
        try:
            spec.loader.exec_module(probe)
        finally:
            sys.dont_write_bytecode = previous
        for control in ("valid", "missing", "additional", "pyc", "pyo"):
            with self.subTest(control=control), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp).resolve()
                package = folder / "more_itertools"
                package.mkdir()
                for relative in probe.MODULES.values():
                    (folder / relative).write_bytes(b"# reviewed source\n")
                if control == "missing":
                    (package / "recipes.py").unlink()
                elif control == "additional":
                    (package / "new_helper.py").write_bytes(b"# unreviewed\n")
                elif control in ("pyc", "pyo"):
                    cache = package / "__pycache__"
                    cache.mkdir()
                    (cache / ("more.cached." + control)).write_bytes(b"untrusted bytecode")
                if control == "valid":
                    files, size = probe.capture_scope(folder)
                    self.assertEqual(files, {name: digest(folder / name) for name in probe.MODULES.values()})
                    self.assertEqual(size, 3 * len(b"# reviewed source\n"))
                else:
                    with self.assertRaises(RuntimeError):
                        probe.capture_scope(folder)

    def test_runtime_or_incomplete_scope_receipts_cannot_complete_the_task(self):
        original = read(EXAMPLE / "fixed-source.json")
        actual311 = read(EXAMPLE / "results.json")["fixed_python311"]
        self.assertEqual(len(actual311["tests"]), 12)
        self.assertTrue(all(row["status"] == "PASS" for row in actual311["tests"]))
        for control in ("runtime", "missing-file", "extra-file"):
            with self.subTest(control=control), tempfile.TemporaryDirectory() as tmp:
                source = copy.deepcopy(original)
                receipt = source["observations"][1]["value"]
                if control == "runtime":
                    receipt["runtime"] = actual311["runtime"]
                elif control == "missing-file":
                    del receipt["code_scope"]["more_itertools/recipes.py"]
                else:
                    receipt["code_scope"]["more_itertools/new_helper.py"] = "0" * 64
                folder = Path(tmp)
                (folder / "source.json").write_bytes(E.encode(source))
                question = read(EXAMPLE / "fixed-complete.json")
                question["source_sha256"] = digest(folder / "source.json")
                (folder / "question.json").write_bytes(E.encode(question))
                result = R.read_requirements(folder / "question.json", digest(folder / "question.json"), folder / "source.json")
                self.assertEqual(result["status"], "INSUFFICIENT")
                self.assertNotIn("requirements", result)
                expected = "runtime" if control == "runtime" else "package-code"
                self.assertEqual(result["relation_gaps"], [{"id": expected, "reason": "MISMATCH"}])


if __name__ == "__main__":
    unittest.main()
