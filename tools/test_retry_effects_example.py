"""Validate saved sequential-retry evidence without installing TinyDB."""
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
EX = ROOT / "examples/retry_effects"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
CANARY = {"1": {"sentinel": "X37 keep unrelated data"}}


def load_probe():
    spec = importlib.util.spec_from_file_location("retry_example_probe", EX / "probe.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class RetryEffectsExample(unittest.TestCase):
    def test_frozen_inputs_and_independent_effect_oracle(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        self.assertEqual(sha(EX / "probe.py"), result["probe_sha256"])
        for name, pin in result["input_sha256"].items():
            self.assertEqual(sha(EX / name), pin)
            raw = (EX / name).read_bytes()
            self.assertEqual(canonical_release_bytes("examples/retry_effects/" + name, raw), raw)
        for policy, record in result["variants"].items():
            expected_policy = contract["variants"][policy]
            self.assertEqual(len(record["tests"]), 12)
            self.assertEqual({r["id"] for r in record["tests"]}, set(oracle))
            for row in record["tests"]:
                expected = oracle[row["id"]]
                wanted = {"canary": CANARY, "_default": {str(i + 1): doc for i, doc in enumerate(expected["documents"])}}
                effect_ok = row["documents"] == expected["documents"] and row["final_state"] == wanted and row["execution_writes"] == expected["execution_writes"]
                self.assertEqual(row["responses"], expected["responses"])
                self.assertEqual(len(row["attempt_trace"]), expected["attempts"])
                self.assertEqual(row["outcome_status"], "PASS")
                self.assertEqual(row["effect_status"], "PASS" if effect_ok else "FAIL")
                self.assertEqual(row["status"], row["effect_status"])
                self.assertEqual(effect_ok, row["id"] not in expected_policy["failed_ids"])
                self.assertEqual(row["final_state"], row["attempt_trace"][-1]["state_after"])
                self.assertTrue(all(t["state_after"]["canary"] == CANARY for t in row["attempt_trace"]))
            self.assertEqual(sum(t["execution_writes"] for t in record["tests"]), expected_policy["execution_writes"])
            self.assertEqual(sum(t["setup_writes"] for t in record["tests"]), 14)
            self.assertEqual(sum(len(t["attempt_trace"]) for t in record["tests"]), 23)
            receipt = read(EX / (policy + "-source.json"))["observations"][1]["value"]
            actual = {k: v for k, v in receipt.items() if k not in ("outcome_passed_ids", "effect_passed_ids")}
            self.assertEqual(actual, record)
            self.assertEqual(receipt["effect_passed_ids"], [t["id"] for t in record["tests"] if t["effect_status"] == "PASS"])
            self.assertEqual(receipt["outcome_passed_ids"], contract["case_ids"])
        self.assertEqual(result["upstream_pytest"]["passed"], 204)
        self.assertEqual(result["upstream_pytest"]["exit_code"], 0)

    def test_attempt_traces_show_lost_ack_and_distinct_intent(self):
        variants = read(EX / "results.json")["variants"]
        rows = {p: {r["id"]: r for r in v["tests"]} for p, v in variants.items()}
        for policy in variants:
            retry = rows[policy]["retry_after_commit"]["attempt_trace"]
            self.assertEqual([t["request_id"] for t in retry], ["X37_A", "X37_A"])
            self.assertEqual([t["injected_error"] for t in retry], ["after_commit", None])
            self.assertEqual(len(retry[0]["state_after"]["_default"]), 1)
            before = rows[policy]["preserve_before_commit_failure"]["attempt_trace"]
            self.assertEqual(before[0]["injected_error"], "before_commit")
            self.assertEqual(before[0]["state_after"], {"canary": CANARY})
            self.assertEqual(len(before[1]["state_after"]["_default"]), 1)
            conflict = rows[policy]["preserve_conflict"]["attempt_trace"]
            self.assertEqual(conflict[-1]["response"], "conflict")
            self.assertEqual(conflict[0]["state_after"], conflict[1]["state_after"])
        self.assertEqual(len(rows["plain_insert"]["retry_after_commit"]["documents"]), 2)
        fixed = rows["request_key"]["retry_after_commit"]["attempt_trace"]
        self.assertEqual(fixed[0]["state_after"], fixed[1]["state_after"])
        self.assertEqual(len(rows["request_key"]["preserve_distinct_same_payload"]["documents"]), 2)
        dropped = rows["payload_key"]["preserve_distinct_same_payload"]
        self.assertEqual(dropped["responses"], ["accepted", "accepted"])
        self.assertEqual(len(dropped["documents"]), 1)

    def test_documented_questions_preserve_all_observations(self):
        doc = (ROOT / "docs/retry-effects-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 6)
        for command, code in zip(commands, (0, 1, 0, 0, 0, 1)):
            args = shlex.split(command)
            args[0] = sys.executable
            run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            view = json.loads(run.stdout)
            if code:
                self.assertEqual(view["relation_gaps"], [{"id": "retry-effects", "reason": "MISMATCH"}])
                self.assertNotIn("requirements", view)
            else:
                source = read(ROOT / args[args.index("--source") + 1])
                self.assertEqual([o for r in view["requirements"] for o in r["observations"]], source["observations"])

    def test_missing_effect_evidence_fails_without_partial_results(self):
        source = read(EX / "request_key-source.json")
        del source["observations"][1]["value"]["effect_passed_ids"]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "source.json").write_bytes(E.encode(source))
            question = read(EX / "request_key-complete.json")
            question["source_sha256"] = sha(folder / "source.json")
            (folder / "question.json").write_bytes(E.encode(question))
            view = R.read_requirements(folder / "question.json", sha(folder / "question.json"), folder / "source.json")
            self.assertEqual(view["status"], "INSUFFICIENT")
            self.assertEqual(view["relation_gaps"], [{"id": "retry-effects", "reason": "MISSING"}])
            self.assertNotIn("requirements", view)

    def test_unreviewed_input_and_existing_scratch_are_rejected(self):
        probe = load_probe()
        manifest, oracle = read(EX / "request_key.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        with self.assertRaises(ValueError):
            probe.read_pinned(EX / "request_key.json", "0" * 64)
        for kind in ("path", "duplicate", "policy", "fault", "initial", "integer", "missing"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "path":
                m["cases"][0]["id"] = "../outside"
            elif kind == "duplicate":
                m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "policy":
                m["policy"] = "parallel"
            elif kind == "fault":
                m["cases"][0]["operations"][0]["fault"] = "power_loss"
            elif kind == "initial":
                m["cases"][0]["initial"] = [{"request_id": "X37_A", "payload": "a"}] * 2
            elif kind == "integer":
                o["expected"]["retry_after_commit"]["execution_writes"] = True
            else:
                del m["cases"][0]["operations"][0]["fault"]
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
