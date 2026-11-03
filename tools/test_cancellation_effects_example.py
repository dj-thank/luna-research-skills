"""Check saved cancellation evidence without importing external schedule."""
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
from unittest.mock import patch

import read_evidence as E
import read_requirements as R
from build_release import canonical_release_bytes

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples/cancellation_effects"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def load_probe():
    spec = importlib.util.spec_from_file_location("cancellation_example_probe", EX / "probe.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class CancellationEffectsExample(unittest.TestCase):
    def test_pins_and_independent_effect_oracle(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        self.assertEqual(sha(EX / "probe.py"), result["probe_sha256"])
        for name, pin in result["input_sha256"].items():
            self.assertEqual(sha(EX / name), pin)
            raw = (EX / name).read_bytes()
            self.assertEqual(canonical_release_bytes("examples/cancellation_effects/" + name, raw), raw)
        for policy, record in result["variants"].items():
            wanted_policy = contract["variants"][policy]
            self.assertEqual(len(record["tests"]), 12)
            self.assertEqual({t["id"] for t in record["tests"]}, set(oracle))
            for row in record["tests"]:
                expected = oracle[row["id"]]
                effect_ok = row["effects"] == expected["effects"] and row["write_count"] == expected["writes"]
                self.assertEqual(row["acknowledgments"], expected["acknowledgments"])
                self.assertEqual(row["callback_count"], expected["callbacks"])
                self.assertEqual(row["controller_calls"], 1)
                self.assertEqual(row["pending_jobs"], 0)
                self.assertEqual(row["drain_returns"], [None, None])
                self.assertEqual(row["outcome_status"], "PASS")
                self.assertEqual(row["effect_status"], "PASS" if effect_ok else "FAIL")
                self.assertEqual(row["status"], row["effect_status"])
                self.assertEqual(effect_ok, row["id"] not in wanted_policy["failed_ids"])
                self.assertEqual(row["callback_count"], sum(t["event"] == "callback" for t in row["trace"]))
                self.assertEqual(row["write_count"], sum(t.get("decision") == "write" for t in row["trace"]))
            self.assertEqual(sum(t["write_count"] for t in record["tests"]), wanted_policy["writes"])
            self.assertEqual(sum(t["callback_count"] for t in record["tests"]), 17)
            receipt = read(EX / (policy + "-source.json"))["observations"][1]["value"]
            self.assertEqual({k: v for k, v in receipt.items() if k not in ("outcome_passed_ids", "effect_passed_ids")}, record)
            self.assertEqual(receipt["outcome_passed_ids"], contract["case_ids"])
            self.assertEqual(receipt["effect_passed_ids"], [t["id"] for t in record["tests"] if t["effect_status"] == "PASS"])
        self.assertFalse(result["upstream_suite"]["executed"])
        self.assertEqual(result["generation_guard_python311"]["tests"], result["variants"]["generation_guard"]["tests"])

    def test_captured_callbacks_and_later_generations(self):
        variants = read(EX / "results.json")["variants"]
        rows = {p: {r["id"]: r for r in v["tests"]} for p, v in variants.items()}
        for policy in variants:
            captured = rows[policy]["captured_cancel"]
            callback = next(t for t in captured["trace"] if t["event"] == "callback")
            self.assertFalse(callback["still_scheduled"])
            self.assertFalse(callback["current_valid"])
            self.assertEqual(callback["decision"], "write" if policy == "unschedule_only" else "discard")
            self.assertEqual(rows[policy]["preserve_before_batch_cancel"]["callback_count"], 0)
            completed = rows[policy]["preserve_cancel_after_completion"]
            self.assertEqual(completed["first_drain_effects"], completed["effects"])
            self.assertEqual(len(completed["effects"]), 1)
        for case in ("replace_same_name", "replace_same_payload", "stale_cancel_new_generation"):
            self.assertEqual([e["generation"] for e in rows["generation_guard"][case]["effects"]], [2])
            self.assertEqual([e["generation"] for e in rows["unschedule_only"][case]["effects"]], [1, 2])
            self.assertEqual(rows["name_tombstone"][case]["effects"], [])
        self.assertEqual(rows["name_tombstone"]["preserve_later_reuse"]["effects"], [])
        self.assertEqual([e["request_id"] for e in rows["generation_guard"]["preserve_cancel_other"]["effects"]], ["X38_A", "X38_C"])

    def test_documented_questions_preserve_observations(self):
        doc = (ROOT / "docs/cancellation-effects-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 6)
        for command, code in zip(commands, (0, 1, 0, 0, 0, 1)):
            args = shlex.split(command)
            args[0] = sys.executable
            run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            view = json.loads(run.stdout)
            if code:
                self.assertEqual(view["relation_gaps"], [{"id": "cancellation-effects", "reason": "MISMATCH"}])
                self.assertNotIn("requirements", view)
            else:
                source = read(ROOT / args[args.index("--source") + 1])
                self.assertEqual([o for r in view["requirements"] for o in r["observations"]], source["observations"])

    def test_missing_effect_evidence_has_no_partial_success(self):
        source = read(EX / "generation_guard-source.json")
        del source["observations"][1]["value"]["effect_passed_ids"]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "source.json").write_bytes(E.encode(source))
            question = read(EX / "generation_guard-complete.json")
            question["source_sha256"] = sha(folder / "source.json")
            (folder / "question.json").write_bytes(E.encode(question))
            view = R.read_requirements(folder / "question.json", sha(folder / "question.json"), folder / "source.json")
            self.assertEqual(view["status"], "INSUFFICIENT")
            self.assertEqual(view["relation_gaps"], [{"id": "cancellation-effects", "reason": "MISSING"}])
            self.assertNotIn("requirements", view)

    def test_refused_inputs_and_existing_scratch(self):
        probe = load_probe()
        manifest, oracle = read(EX / "generation_guard.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        with self.assertRaises(ValueError):
            probe.read_pinned(EX / "generation_guard.json", "0" * 64)
        for kind in ("path", "duplicate", "policy", "unknown_cancel", "generation", "reuse", "count", "schema", "command"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "path": m["cases"][0]["id"] = "../outside"
            elif kind == "duplicate": m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "policy": m["policy"] = "parallel"
            elif kind == "unknown_cancel": m["cases"][0]["during"][0]["generation"] = 2
            elif kind == "generation": m["cases"][0]["initial"][0]["generation"] = True
            elif kind == "reuse": m["cases"][3]["during"][1]["generation"] = 1
            elif kind == "count": o["expected"]["captured_cancel"]["callbacks"] = True
            elif kind == "schema": m["schema_version"] = True
            else: m["cases"][0]["initial"][0] = None
            with self.assertRaises(ValueError):
                probe.validate(m, o)
        with tempfile.TemporaryDirectory() as folder, patch.object(probe, "capture_scope", return_value={}):
            folder = Path(folder)
            keep = folder / "existing.txt"
            keep.write_bytes(b"preserve existing content")
            with self.assertRaises(ValueError):
                probe.run(folder, manifest, oracle, folder)
            self.assertEqual(list(folder.iterdir()), [keep])
            self.assertEqual(keep.read_bytes(), b"preserve existing content")


if __name__ == "__main__":
    unittest.main()
