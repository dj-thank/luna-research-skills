"""Check partial-failure evidence without importing historical more-itertools."""
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
from build_release import canonical_release_bytes

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples/partial_failure"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

class PartialFailureExample(unittest.TestCase):
    def test_pins_and_literal_answers(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        self.assertEqual(sha(EX / "probe.py"), result["probe_sha256"])
        pins = {**result["input_sha256"], **result["patch_sha256"],
                **{k + ".py": v for k, v in result["callsite_sha256"].items()}}
        for name, pin in pins.items():
            raw = (EX / name).read_bytes()
            self.assertEqual(sha(EX / name), pin)
            self.assertEqual(canonical_release_bytes("examples/partial_failure/" + name, raw), raw)
        for variant, record in result["variants"].items():
            self.assertEqual([r["id"] for r in record["tests"]], contract["case_ids"])
            self.assertEqual(len(record["code_scope"]), 6)
            self.assertEqual(record["callsite_sha256"], result["callsite_sha256"][variant])
            for row in record["tests"]:
                for part in ("terminal", "state"):
                    self.assertEqual(row[part + "_status"], "PASS" if row[part] == oracle[row["id"]][part] else "FAIL")
                self.assertEqual(row["status"], "PASS" if row["terminal_status"] == row["state_status"] == "PASS" else "FAIL")
            self.assertEqual([r["id"] for r in record["tests"] if r["status"] == "FAIL"], contract["variants"][variant]["failed_ids"])
            source = read(EX / (variant + "-source.json"))
            proposal, receipt = [o["value"] for o in source["observations"][:2]]
            self.assertEqual({k: v for k, v in receipt.items() if k not in ("actual_terminal", "actual_state")}, record)
            self.assertEqual(proposal["expected_state"], {k: v["state"] for k, v in oracle.items()})
            self.assertEqual(proposal["expected_terminal"], {k: v["terminal"] for k, v in oracle.items()})
            for row in record["tests"]:
                self.assertEqual(receipt["actual_state"][row["id"]], row["state"])
                self.assertEqual(receipt["actual_terminal"][row["id"]], row["terminal"])
        self.assertTrue(all(v["executed"] and not v["full_suite"] and v["failed"] == 0 for v in result["upstream_doctests"].values()))

    def test_cleanup_and_prefix_are_separate_from_exception(self):
        result = read(EX / "results.json")
        rows = {v: {r["id"]: r for r in report["tests"]} for v, report in result["variants"].items()}
        old, fixed, swallowed = [rows[v]["source_two"] for v in ("base", "fixed", "swallow")]
        self.assertEqual(old["terminal"], fixed["terminal"])
        self.assertEqual(old["state"]["outputs"], ["a", "b"])
        self.assertFalse(old["state"]["resource_closed"])
        self.assertEqual(old["state"]["exit_count"], 0)
        self.assertTrue(fixed["state"]["resource_closed"])
        self.assertEqual(fixed["state"]["exit_errors"], ["InjectedError"])
        self.assertEqual(swallowed["state"], fixed["state"])
        self.assertIsNone(swallowed["terminal"])
        for variant in rows:
            self.assertFalse(rows[variant]["consumer_two"]["state"]["source_finalized"])
            self.assertEqual(rows[variant]["consumer_two"]["state"]["source_seen"], ["a", "b", "c"])
            self.assertEqual(rows[variant]["consumer_two"]["state"]["outputs"], ["a", "b"])
            self.assertEqual(rows[variant]["duplicates"]["state"]["written"], "a\na\nb\n")

    def test_documented_questions_keep_observations(self):
        doc = (ROOT / "docs/partial-failure-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 6)
        for command, code in zip(commands, (0, 1, 0, 0, 1, 1)):
            args = shlex.split(command); args[0] = sys.executable
            run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            view = json.loads(run.stdout)
            if code:
                self.assertNotIn("requirements", view)
                self.assertEqual(view["relation_gaps"][0]["reason"], "MISMATCH")
            else:
                source = read(ROOT / args[args.index("--source") + 1])
                self.assertEqual([o for r in view["requirements"] for o in r["observations"]], source["observations"])

    def test_missing_cleanup_and_lost_prefix_are_rejected(self):
        for missing in (True, False):
            source = read(EX / "fixed-source.json")
            receipt = source["observations"][1]["value"]
            terminals = copy.deepcopy(receipt["actual_terminal"])
            if missing:
                del receipt["actual_state"]
            else:
                receipt["actual_state"]["source_two"]["outputs"] = ["b"]
                receipt["actual_state"]["source_two"]["written"] = "b\n"
                row = next(r for r in receipt["tests"] if r["id"] == "source_two")
                row["state"]["outputs"] = ["b"]; row["state"]["written"] = "b\n"
                row["state_status"] = row["status"] = "FAIL"
            self.assertEqual(terminals, receipt["actual_terminal"])
            with tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                (folder / "source.json").write_bytes(E.encode(source))
                question = read(EX / "fixed-complete.json")
                question["source_sha256"] = sha(folder / "source.json")
                (folder / "question.json").write_bytes(E.encode(question))
                view = R.read_requirements(folder / "question.json", sha(folder / "question.json"), folder / "source.json")
                self.assertEqual(view["status"], "INSUFFICIENT")
                self.assertEqual(view["relation_gaps"], [{"id": "state", "reason": "MISSING" if missing else "MISMATCH"}])
                self.assertNotIn("requirements", view)

    def test_bounded_probe_inputs(self):
        spec = importlib.util.spec_from_file_location("partial_failure_probe", EX / "probe.py")
        probe = importlib.util.module_from_spec(spec)
        previous = sys.dont_write_bytecode
        try:
            spec.loader.exec_module(probe)
        finally:
            sys.dont_write_bytecode = previous
        manifest, oracle = read(EX / "manifest.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        with self.assertRaises(ValueError):
            probe.read_pinned(EX / "manifest.json", "0" * 64)
        for kind in ("offset", "bool_offset", "fault", "duplicate", "schema", "empty", "oracle", "state_bool", "exit", "long_value"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "offset": m["cases"][8]["at"] = 4
            elif kind == "bool_offset": m["cases"][0]["at"] = True
            elif kind == "fault": m["cases"][0]["fault"] = "network"
            elif kind == "duplicate": m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "schema": m["schema_version"] = True
            elif kind == "empty": m["cases"] = []
            elif kind == "oracle": del o["expected"]["single"]
            elif kind == "state_bool": o["expected"]["single"]["state"]["resource_closed"] = 1
            elif kind == "exit": o["expected"]["single"]["state"]["exit_count"] = True
            else: m["cases"][1]["items"] = ["x" * 65]
            with self.assertRaises(ValueError):
                probe.validate(m, o)

if __name__ == "__main__":
    unittest.main()
