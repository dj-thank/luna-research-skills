"""Check saved ordered-record evidence without importing external Boltons."""
from collections import Counter
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
EX = ROOT / "examples/ordered_records"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


class OrderedRecordsExample(unittest.TestCase):
    def test_pins_and_literal_records(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        self.assertEqual(sha(EX / "probe.py"), result["probe_sha256"])
        for name, pin in {**result["input_sha256"], **result["patch_sha256"]}.items():
            self.assertEqual(sha(EX / name), pin)
            raw = (EX / name).read_bytes()
            self.assertEqual(canonical_release_bytes("examples/ordered_records/" + name, raw), raw)
        for variant, record in result["variants"].items():
            self.assertEqual([r["id"] for r in record["tests"]], contract["case_ids"])
            self.assertEqual(len(record["code_scope"]), 30)
            for row in record["tests"]:
                kind, key = row["id"].split(":")
                wanted = oracle[key]
                expected = {"pairs": wanted["pairs"], "query": wanted["query"] if kind == "query" else None}
                self.assertEqual(row["counts"]["unique_keys"], wanted["unique_keys"])
                self.assertEqual(row["count_status"], "PASS")
                self.assertEqual(row["record_status"], "PASS" if row["records"] == expected else "FAIL")
                self.assertEqual(row["status"], row["record_status"])
                self.assertEqual(row["records"] != expected, row["id"] in contract["variants"][variant]["failed_ids"])
            source = read(EX / (variant + "-source.json"))
            proposal, receipt = [o["value"] for o in source["observations"][:2]]
            self.assertEqual({k: v for k, v in receipt.items() if k not in ("actual_counts", "actual_records")}, record)
            self.assertEqual(proposal["code_scope"], record["code_scope"])
            self.assertEqual(proposal["expected_counts"], receipt["actual_counts"])
            for row in record["tests"]:
                self.assertEqual(receipt["actual_records"][row["id"]], row["records"])
                self.assertEqual(receipt["actual_counts"][row["id"]], row["counts"])
            self.assertFalse(record["network_or_installation_performed"])
        self.assertEqual(result["fixed_python311"]["tests"], result["variants"]["fixed"]["tests"])
        self.assertTrue(all(r["executed"] and not r["full_suite"] for r in result["upstream_subsets"].values()))

    def test_duplicate_loss_and_representation_equivalence(self):
        result = read(EX / "results.json")
        rows = {v: {r["id"]: r for r in report["tests"]} for v, report in result["variants"].items()}
        for kind in ("omd", "query"):
            for variant in rows:
                self.assertEqual(rows[variant][kind + ":new_pair"]["counts"]["unique_keys"], 1)
            self.assertEqual(rows["base"][kind + ":new_pair"]["records"]["pairs"], [["tag", "r2"]])
            self.assertEqual(rows["fixed"][kind + ":new_pair"]["records"]["pairs"], [["tag", "r1"], ["tag", "r2"]])
            self.assertEqual(rows["fixed"][kind + ":equal_values"]["records"]["pairs"], [["tag", "same"], ["tag", "same"]])
            self.assertEqual(rows["dedup"][kind + ":equal_values"]["records"]["pairs"], [["tag", "same"]])
            for variant in rows:
                group = [rows[variant][kind + ":" + key]["records"] for key in ("new_pair", "iterator_twice", "omd_equivalent")]
                agreement = all(v == group[0] for v in group)
                self.assertEqual(agreement, variant == "fixed")
                self.assertEqual(agreement, result["handoff_comparison"]["metamorphic_representation_agreement"][variant][kind])
                self.assertEqual(rows[variant][kind + ":keyword_override"]["records"]["pairs"], [["keep", "p1"], ["tag", "final"]])

    def test_documented_questions_preserve_observations(self):
        doc = (ROOT / "docs/ordered-records-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 6)
        for command, code in zip(commands, (0, 1, 0, 0, 0, 1)):
            args = shlex.split(command)
            args[0] = sys.executable
            run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            view = json.loads(run.stdout)
            if code:
                self.assertNotIn("requirements", view)
                self.assertEqual(view["relation_gaps"], [{"id": "records", "reason": "MISMATCH"}])
            else:
                source = read(ROOT / args[args.index("--source") + 1])
                self.assertEqual([o for r in view["requirements"] for o in r["observations"]], source["observations"])

    def test_missing_and_order_only_corruption(self):
        for missing in (True, False):
            source = read(EX / "fixed-source.json")
            receipt = source["observations"][1]["value"]
            counts = copy.deepcopy(receipt["actual_counts"])
            if missing:
                del receipt["actual_records"]
            else:
                before = receipt["actual_records"]["omd:unique"]["pairs"]
                after = sorted(before)
                self.assertNotEqual(before, after)
                self.assertEqual(Counter(map(tuple, before)), Counter(map(tuple, after)))
                receipt["actual_records"]["omd:unique"]["pairs"] = after
                row = next(r for r in receipt["tests"] if r["id"] == "omd:unique")
                row["records"]["pairs"] = after
                row["record_status"] = row["status"] = "FAIL"
            self.assertEqual(counts, receipt["actual_counts"])
            with tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                (folder / "source.json").write_bytes(E.encode(source))
                question = read(EX / "fixed-complete.json")
                question["source_sha256"] = sha(folder / "source.json")
                (folder / "question.json").write_bytes(E.encode(question))
                view = R.read_requirements(folder / "question.json", sha(folder / "question.json"), folder / "source.json")
                self.assertEqual(view["status"], "INSUFFICIENT")
                self.assertEqual(view["relation_gaps"], [{"id": "records", "reason": "MISSING" if missing else "MISMATCH"}])
                self.assertNotIn("requirements", view)

    def test_bounded_inputs_and_pins(self):
        spec = importlib.util.spec_from_file_location("ordered_example_probe", EX / "probe.py")
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
        for kind in ("source", "pair_type", "pair_length", "long_value", "duplicate", "schema", "empty", "missing_oracle", "count_bool", "keywords"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "source": m["cases"][0]["source"] = "network"
            elif kind == "pair_type": m["cases"][0]["pairs"][0][1] = {}
            elif kind == "pair_length": m["cases"][0]["pairs"][0].append("extra")
            elif kind == "long_value": m["cases"][0]["pairs"][0][1] = "x" * 129
            elif kind == "duplicate": m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "schema": m["schema_version"] = True
            elif kind == "empty": m["cases"] = []
            elif kind == "missing_oracle": del o["expected"]["unique"]
            elif kind == "count_bool": o["expected"]["unique"]["unique_keys"] = True
            else: m["cases"][0]["keywords"]["a"] = None
            with self.assertRaises(ValueError):
                probe.validate(m, o)


if __name__ == "__main__":
    unittest.main()
