"""Verify the JSON transfer fixtures without importing external simplejson."""
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
EX = ROOT / "examples/json_input_transfer"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class JsonInputTransferExample(unittest.TestCase):
    def test_pinned_inputs_and_known_answers(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        self.assertEqual(oracle["bom_object"], {"value": {"number": 7}, "error_kind": None})
        self.assertEqual(oracle["inner_bom"], {"value": {"content": "a\ufeffb"}, "error_kind": None})
        for name, field in (("probe.py", "probe_sha256"), ("manifest.json", "manifest_sha256"), ("oracle.json", "oracle_sha256"), ("accepted.patch", "patch_sha256")):
            self.assertEqual(sha(EX / name), result[field])
        for folder, field in (("inputs", "input_sha256"), ("stale-inputs", "stale_input_sha256")):
            self.assertEqual({p.name: sha(p) for p in (EX / folder).iterdir()}, result[field])
        for name, pin in result["snapshot_manifest_sha256"].items():
            self.assertEqual(sha(EX / (name + "-source-manifest.json")), pin)
        for variant, report in result["variants"].items():
            self.assertTrue(report["pure_python"])
            self.assertTrue(set(report["imported_target_modules"].values()).issubset(report["code_scope"]))
            self.assertEqual(report["code_scope"], contract["code_scopes"][contract["variants"][variant]["code"]])
            self.assertEqual([row["id"] for row in report["tests"]], contract["case_ids"])
            for row in report["tests"]:
                self.assertEqual(row["status"], "PASS" if encode(row["actual"]) == encode(oracle[row["id"]]) else "FAIL")
                self.assertEqual(row["actual"], report["actual_outputs"][row["id"]])
                self.assertEqual(row["input"], report["actual_inputs"][row["id"]])
                folder = "stale-inputs" if variant == "stale" else "inputs"
                raw = (EX / folder / row["input"]["path"]).read_bytes()
                self.assertEqual(row["input"], {"path": row["input"]["path"], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            self.assertEqual([row["id"] for row in report["tests"] if row["status"] == "FAIL"], contract["variants"][variant]["failed_ids"])
            self.assertEqual(read(EX / (variant + "-source.json"))["observations"][1]["value"], report)
        self.assertEqual(result["variants"]["base"]["code_scope"], result["variants"]["stale"]["code_scope"])
        self.assertEqual(result["variants"]["fixed"]["actual_outputs"], result["variants"]["stale"]["actual_outputs"])
        changed = contract["variants"]["stale"]["input_mismatch_ids"]
        self.assertEqual(set(changed), {"bom_object", "bom_array", "bom_scalar", "bom_japanese"})
        for case, identity in contract["expected_inputs"].items():
            wanted = (EX / "inputs" / identity["path"]).read_bytes()
            stale = (EX / "stale-inputs" / identity["path"]).read_bytes()
            self.assertEqual(stale, wanted[3:] if case in changed else wanted)
            if case in changed: self.assertTrue(wanted.startswith(b"\xef\xbb\xbf"))
        self.assertEqual([result["upstream_tests"][n]["count"] for n in ("base", "fixed")], [2, 3])

    def test_documented_decisions_preserve_all_evidence(self):
        commands = re.findall(r"^python tools/read_requirements.py .+$", (ROOT / "docs/json-input-transfer.md").read_text(encoding="utf-8"), re.M)
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
                self.assertEqual([o for req in view["requirements"] for o in req["observations"]], source["observations"])
                self.assertEqual(view["metrics"]["source_reads"], 1)
        previous = read(ROOT / "examples/input_provenance/fixed-inputs.json")
        self.assertEqual(read(EX / "fixed-inputs.json")["relations"], previous["relations"])

    def test_missing_and_same_value_swapped_inputs_are_rejected(self):
        fixed = read(EX / "fixed-source.json")["observations"][1]["value"]
        self.assertEqual(fixed["actual_outputs"]["bom_object"], fixed["actual_outputs"]["plain_object"])
        for name, reason in (("missing_inputs", "MISSING"), ("case_mapping_swapped", "MISMATCH")):
            receipt = read(EX / (name + "-source.json"))["observations"][1]["value"]
            self.assertEqual(receipt["actual_outputs"], fixed["actual_outputs"])
            if name == "case_mapping_swapped":
                bag = lambda mapping: collections.Counter(encode(value) for value in mapping.values())
                self.assertEqual(bag(receipt["actual_inputs"]), bag(fixed["actual_inputs"]))
            for policy, status in (("code", "OBSERVED"), ("inputs", "INSUFFICIENT")):
                q = EX / (name + "-" + policy + ".json")
                view = R.read_requirements(q, sha(q), EX / (name + "-source.json"))
                self.assertEqual(view["status"], status)
                if policy == "inputs":
                    self.assertEqual(view["relation_gaps"], [{"id": "inputs", "reason": reason}])
                    self.assertNotIn("requirements", view)

    def test_probe_boundaries_and_type_sensitive_matching(self):
        spec = importlib.util.spec_from_file_location("json_transfer_probe", EX / "probe.py")
        probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
        manifest, oracle = read(EX / "manifest.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        self.assertNotEqual(probe.canonical({"value": True}), probe.canonical({"value": 1}))
        with self.assertRaises(ValueError): probe.read_pinned(EX / "manifest.json", "0" * 64)
        for kind in ("path", "api", "representation", "duplicate", "schema", "count", "oracle", "error"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "path": m["cases"][0]["file"] = "../escape.bin"
            elif kind == "api": m["cases"][0]["api"] = "dump"
            elif kind == "representation": m["cases"][0]["representation"] = "utf-8-sig"
            elif kind == "duplicate": m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "schema": m["schema_version"] = True
            elif kind == "count": m["cases"] *= 2
            elif kind == "oracle": del o["expected"]["empty"]
            else: o["expected"]["empty"]["value"] = 1
            with self.assertRaises(ValueError): probe.validate(m, o)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "large.json"; p.write_bytes(b"x" * 65537)
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))
            p.write_bytes(b'{"a":1,"a":2}')
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))


if __name__ == "__main__":
    unittest.main()
