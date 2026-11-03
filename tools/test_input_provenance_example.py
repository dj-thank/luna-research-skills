"""Check frozen input-bound receipts without importing external ConfigArgParse."""
import collections
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

import read_requirements as R

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples/input_provenance"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

class InputProvenanceExample(unittest.TestCase):
    def test_pins_and_literal_outputs(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        for name, field in (("probe.py", "probe_sha256"), ("manifest.json", "manifest_sha256"), ("oracle.json", "oracle_sha256"), ("accepted.patch", "patch_sha256")):
            self.assertEqual(sha(EX / name), result[field])
        for folder, field in (("inputs", "input_sha256"), ("stale-inputs", "stale_input_sha256")):
            for name, pin in result[field].items():
                self.assertEqual(sha(EX / folder / name), pin)
        for name, pin in result["snapshot_manifest_sha256"].items():
            self.assertEqual(sha(EX / (name + "-source-manifest.json")), pin)
        for variant, report in result["variants"].items():
            self.assertEqual(report["code_scope"], contract["code_scopes"][contract["variants"][variant]["code"]])
            self.assertEqual([t["id"] for t in report["tests"]], contract["case_ids"])
            for row in report["tests"]:
                self.assertEqual(row["status"], "PASS" if row["actual"] == oracle[row["id"]] else "FAIL")
                self.assertEqual(row["actual"], report["actual_outputs"][row["id"]])
                self.assertEqual(row["input"], report["actual_inputs"][row["id"]])
                folder = "stale-inputs" if variant == "stale" else "inputs"
                raw = (EX / folder / row["input"]["path"]).read_bytes()
                self.assertEqual(row["input"]["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(row["input"]["bytes"], len(raw))
            self.assertEqual([t["id"] for t in report["tests"] if t["status"] == "FAIL"], contract["variants"][variant]["failed_ids"])
            self.assertEqual(read(EX / (variant + "-source.json"))["observations"][1]["value"], report)
        self.assertEqual(result["upstream_tests"]["base"]["count"], 1)
        self.assertEqual(result["upstream_tests"]["fixed"]["count"], 3)
        self.assertTrue(all(r["exit_code"] == 0 and not r["full_suite"] for r in result["upstream_tests"].values()))

    def test_stale_data_hides_five_real_failures_in_unfixed_code(self):
        rows = read(EX / "results.json")["variants"]
        self.assertEqual(rows["base"]["code_scope"], rows["stale"]["code_scope"])
        self.assertEqual(rows["fixed"]["actual_outputs"], rows["stale"]["actual_outputs"])
        expected = read(EX / "contract.json")["expected_inputs"]
        changed = [name for name, value in rows["stale"]["actual_inputs"].items() if value != expected[name]]
        self.assertEqual(set(changed), {"cli_disables", "cli_enables", "cli_short", "cli_long", "env_overrides"})
        self.assertEqual(sum(t["status"] == "PASS" for t in rows["base"]["tests"]), 5)
        self.assertEqual(sum(t["status"] == "PASS" for t in rows["fixed"]["tests"]), 10)
        self.assertEqual(sum(t["status"] == "PASS" for t in rows["stale"]["tests"]), 10)

    def test_documented_questions_preserve_every_observation(self):
        commands = re.findall(r"^python tools/read_requirements.py .+$", (ROOT / "docs/input-provenance-evaluation.md").read_text(encoding="utf-8"), re.M)
        self.assertEqual(len(commands), 6)
        for command, code in zip(commands, (1, 1, 0, 0, 0, 1)):
            args = shlex.split(command); args[0] = sys.executable
            run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            view = json.loads(run.stdout)
            if code:
                self.assertEqual(view["status"], "INSUFFICIENT"); self.assertNotIn("requirements", view)
            else:
                source = read(ROOT / args[args.index("--source") + 1])
                self.assertEqual([o for r in view["requirements"] for o in r["observations"]], source["observations"])
                self.assertEqual(view["metrics"]["source_reads"], 1)

    def test_missing_and_swapped_case_bindings_are_refused(self):
        fixed = read(EX / "fixed-source.json")["observations"][1]["value"]
        for name, reason in (("missing_inputs", "MISSING"), ("case_mapping_swapped", "MISMATCH")):
            source = read(EX / (name + "-source.json"))["observations"][1]["value"]
            self.assertEqual(source["actual_outputs"], fixed["actual_outputs"])
            if name == "case_mapping_swapped":
                values = lambda m: collections.Counter(json.dumps(v, sort_keys=True) for v in m.values())
                self.assertEqual(values(source["actual_inputs"]), values(fixed["actual_inputs"]))
            for policy, status in (("code", "OBSERVED"), ("inputs", "INSUFFICIENT")):
                q = EX / (name + "-" + policy + ".json")
                view = R.read_requirements(q, sha(q), EX / (name + "-source.json"))
                self.assertEqual(view["status"], status)
                if policy == "inputs":
                    self.assertEqual(view["relation_gaps"], [{"id": "inputs", "reason": reason}])
                    self.assertNotIn("requirements", view)

    def test_probe_refuses_wrong_pins_and_unsafe_case_inputs(self):
        spec = importlib.util.spec_from_file_location("input_provenance_probe", EX / "probe.py")
        probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
        manifest, oracle = read(EX / "manifest.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        with self.assertRaises(ValueError): probe.read_pinned(EX / "manifest.json", "0" * 64)
        for kind in ("path", "args", "env", "duplicate", "schema", "count", "oracle", "bool_exit", "output"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "path": m["cases"][0]["config"] = "../escape.ini"
            elif kind == "args": m["cases"][0]["args"] = ["--config", "/outside"]
            elif kind == "env": m["cases"][0]["env"] = {"SECRET": "value"}
            elif kind == "duplicate": m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "schema": m["schema_version"] = True
            elif kind == "count": m["cases"] = m["cases"] * 2
            elif kind == "oracle": del o["expected"]["cli_disables"]
            elif kind == "bool_exit": o["expected"]["cli_disables"]["exit_code"] = False
            else: o["expected"]["cli_disables"]["value"] = "wrong"
            with self.assertRaises(ValueError): probe.validate(m, o)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "large.json"; p.write_bytes(b"x" * 65537)
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))
            p.write_bytes(b'{"a":1,"a":2}')
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))

if __name__ == "__main__":
    unittest.main()
