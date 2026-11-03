"""Validate recorded marker semantics without importing external packaging."""
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
EX = ROOT / "examples/marker_roundtrip"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


class MarkerRoundtripExample(unittest.TestCase):
    def test_pins_and_literal_oracle(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        self.assertEqual(sha(EX / "probe.py"), result["probe_sha256"])
        for name, pin in {**result["input_sha256"], **result["patch_sha256"]}.items():
            self.assertEqual(sha(EX / name), pin)
            raw = (EX / name).read_bytes()
            self.assertEqual(canonical_release_bytes("examples/marker_roundtrip/" + name, raw), raw)
        for variant, record in result["variants"].items():
            self.assertEqual(len(record["tests"]), 12)
            self.assertEqual({r["id"] for r in record["tests"]}, set(oracle))
            for row in record["tests"]:
                expected = oracle[row["id"]]
                actual = {key: row["observed"][key] for key in expected}
                self.assertEqual(row["status"], "PASS" if actual == expected else "FAIL")
                self.assertEqual(actual != expected, row["id"] in contract["variants"][variant]["failed_ids"])
            source = read(EX / (variant + "-source.json"))
            proposal, receipt = [o["value"] for o in source["observations"][:2]]
            self.assertEqual({k: v for k, v in receipt.items() if k not in ("repair_passed_ids", "preservation_passed_ids")}, record)
            self.assertEqual(proposal["code_scope"], record["code_scope"])
            self.assertEqual(len(record["code_scope"]), 22)
            for group in ("repair", "preservation"):
                self.assertEqual(receipt[group + "_passed_ids"], [r["id"] for r in record["tests"] if r["id"] in contract[group + "_ids"] and r["status"] == "PASS"])
            self.assertTrue(record["explicit_environment_only_in_receipts"])
            self.assertFalse(record["network_or_installation_performed"])
        self.assertEqual(result["fixed_python311"]["tests"], result["variants"]["fixed"]["tests"])
        self.assertTrue(all(r["executed"] and not r["full_suite"] for r in result["upstream_subsets"].values()))

    def test_quote_injection_and_case_preservation(self):
        variants = read(EX / "results.json")["variants"]
        rows = {v: {r["id"]: r["observed"] for r in report["tests"]} for v, report in variants.items()}
        for case in ("marker_injection", "requirement_injection"):
            self.assertFalse(rows["base"][case]["before"]["evaluation"])
            self.assertTrue(rows["base"][case]["after"]["evaluation"])
            self.assertFalse(rows["fixed"][case]["after"]["evaluation"])
            self.assertEqual(rows["fixed"][case]["before"], rows["fixed"][case]["after"])
        self.assertEqual(rows["base"]["embedded_quote"]["roundtrip_error"], "InvalidMarker")
        self.assertIsNone(rows["base"]["both_quotes"]["serialization_error"])
        self.assertEqual(rows["fixed"]["both_quotes"]["serialization_error"], "ValueError")
        for case in ("uppercase_machine", "implementation_case"):
            self.assertTrue(rows["casefold"][case]["before"]["evaluation"])
            self.assertFalse(rows["casefold"][case]["after"]["evaluation"])
        for variant in rows:
            self.assertEqual(rows[variant]["normalized_extra"]["after"]["literals"], ["foo-bar"])
            self.assertEqual(rows[variant]["requirement_url_case"]["after"]["requirement"]["url"], "https://EXAMPLE.invalid/Path")

    def test_documented_questions_preserve_observations(self):
        doc = (ROOT / "docs/marker-roundtrip-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 6)
        for command, code in zip(commands, (1, 1, 0, 0, 0, 1)):
            args = shlex.split(command)
            args[0] = sys.executable
            run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            view = json.loads(run.stdout)
            if code:
                self.assertNotIn("requirements", view)
                self.assertTrue(all(g["reason"] == "MISMATCH" for g in view["relation_gaps"]))
            else:
                source = read(ROOT / args[args.index("--source") + 1])
                self.assertEqual([o for r in view["requirements"] for o in r["observations"]], source["observations"])

    def test_missing_preservation_has_no_partial_success(self):
        source = read(EX / "fixed-source.json")
        del source["observations"][1]["value"]["preservation_passed_ids"]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "source.json").write_bytes(E.encode(source))
            question = read(EX / "fixed-complete.json")
            question["source_sha256"] = sha(folder / "source.json")
            (folder / "question.json").write_bytes(E.encode(question))
            view = R.read_requirements(folder / "question.json", sha(folder / "question.json"), folder / "source.json")
            self.assertEqual(view["status"], "INSUFFICIENT")
            self.assertEqual(view["relation_gaps"], [{"id": "preservation", "reason": "MISSING"}])
            self.assertNotIn("requirements", view)

    def test_bounded_explicit_environment_and_input_pins(self):
        spec = importlib.util.spec_from_file_location("marker_example_probe", EX / "probe.py")
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
        for kind in ("missing_env", "extra_env", "long_env", "input", "kind", "duplicate", "schema", "empty", "missing_oracle", "extra_observation", "override"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "missing_env": del m["environment"]["os_name"]
            elif kind == "extra_env": m["environment"]["PATH"] = "never read host environment"
            elif kind == "long_env": m["environment"]["os_name"] = "x" * 2049
            elif kind == "input": m["cases"][0]["input"] = "x" * 2049
            elif kind == "kind": m["cases"][0]["kind"] = "install"
            elif kind == "duplicate": m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "schema": m["schema_version"] = True
            elif kind == "empty": m["cases"] = []
            elif kind == "missing_oracle": del o["expected"]["plain_marker"]
            elif kind == "extra_observation": o["expected"]["plain_marker"]["ignored"] = True
            else: m["cases"][0]["overrides"]["HOME"] = "never read host environment"
            with self.assertRaises(ValueError):
                probe.validate(m, o)


if __name__ == "__main__":
    unittest.main()
