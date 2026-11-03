"""Validate saved stream evidence and capture at the actual iterator boundary."""
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
EX = ROOT / "examples/stream_chunks"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
encode = lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_probe():
    spec = importlib.util.spec_from_file_location("stream_chunks_probe", EX / "probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StreamChunksExample(unittest.TestCase):
    def test_pins_known_answers_and_recorded_actual_runs(self):
        result, contract, oracle = read(EX / "results.json"), read(EX / "contract.json"), read(EX / "oracle.json")["expected"]
        self.assertEqual(oracle["three_byte"]["events"][0]["data"], "€")
        self.assertEqual(oracle["japanese"]["events"][0]["data"], "日本")
        self.assertEqual([e["data"] for e in oracle["two_events"]["events"]], ["first", "second"])
        for name, field in (("probe.py", "probe_sha256"), ("manifest.json", "manifest_sha256"), ("oracle.json", "oracle_sha256"), ("accepted.patch", "patch_sha256")):
            self.assertEqual(sha(EX / name), result[field])
        self.assertEqual({p.name: sha(p) for p in (EX / "inputs").iterdir()}, result["input_sha256"])
        for name, pin in result["snapshot_manifest_sha256"].items():
            self.assertEqual(sha(EX / (name + "-source-manifest.json")), pin)
        probe = load_probe()
        for variant, report in result["variants"].items():
            settings = contract["variants"][variant]
            self.assertEqual(report["code_scope"], contract["code_scopes"][settings["code"]])
            self.assertEqual(report["mode"], settings["mode"])
            self.assertEqual([r["id"] for r in report["tests"]], contract["case_ids"])
            self.assertEqual(report["actual_inputs"], contract["expected_inputs"])
            for row in report["tests"]:
                chunks = [bytes.fromhex(c["hex"]) for c in row["delivery"]["chunks"]]
                self.assertEqual(row["delivery"]["chunks"], [probe.byte_identity(c) for c in chunks])
                self.assertEqual(row["buffer"], probe.byte_identity(b"".join(chunks)))
                self.assertEqual(row["status"], "PASS" if encode(row["actual"]) == encode(oracle[row["id"]]) else "FAIL")
                for plural, field in (("outputs", "actual"), ("inputs", "input"), ("buffers", "buffer"), ("deliveries", "delivery")):
                    self.assertEqual(row[field], report["actual_" + plural][row["id"]])
            self.assertEqual([r["id"] for r in report["tests"] if r["status"] == "FAIL"], settings["failed_ids"])
            for plural, field in (("buffers", "buffer"), ("deliveries", "delivery")):
                self.assertEqual([r["id"] for r in report["tests"] if r[field] != contract["expected_" + plural][r["id"]]], settings[field + "_mismatch_ids"])
            self.assertEqual(read(EX / (variant + "-source.json"))["observations"][1]["value"], report)

    def test_same_bytes_different_order_and_legal_segmentations(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        variants = result["variants"]
        fixed = variants["fixed"]
        for name in ("coalesced", "reordered"):
            self.assertEqual(variants[name]["actual_inputs"], fixed["actual_inputs"])
            self.assertEqual(variants[name]["actual_buffers"], fixed["actual_buffers"])
            self.assertEqual(variants[name]["actual_outputs"], fixed["actual_outputs"])
            self.assertNotEqual(variants[name]["actual_deliveries"], fixed["actual_deliveries"])
        a = fixed["actual_deliveries"]["repeat_fragments"]["chunks"]
        b = variants["reordered"]["actual_deliveries"]["repeat_fragments"]["chunks"]
        self.assertEqual(collections.Counter(map(encode, a)), collections.Counter(map(encode, b)))
        self.assertNotEqual(a, b)
        self.assertEqual([bytes.fromhex(c["hex"]) for c in a], [b"data: ", b"A", b"AA", b"\n\n"])
        for name in contract["allowed_segmentations"]:
            self.assertEqual(fixed["actual_outputs"][name], fixed["actual_outputs"]["whole_unicode"])
            self.assertEqual(fixed["actual_buffers"][name], fixed["actual_buffers"]["whole_unicode"])
            self.assertEqual(fixed["actual_deliveries"][name], contract["expected_deliveries"][name])
        dropped = variants["dropped"]["actual_outputs"]["two_events"]["events"]
        self.assertEqual([e["data"] for e in dropped], ["second"])
        self.assertEqual(variants["base"]["code_scope"], variants["coalesced"]["code_scope"])

    def test_decisions_preserve_all_observations(self):
        for record in read(EX / "results.json")["cases"]:
            name = record["id"]
            for policy, expected in zip(("buffer", "chunks"), record["expected_statuses"]):
                q = EX / (name + "-" + policy + ".json")
                source = EX / (name + "-source.json")
                view = R.read_requirements(q, sha(q), source)
                self.assertEqual(view["status"], expected)
                if expected == "OBSERVED":
                    self.assertEqual([o for req in view["requirements"] for o in req["observations"]], read(source)["observations"])
                    self.assertEqual(view["metrics"]["source_reads"], 1)
                else:
                    self.assertNotIn("requirements", view)
                if policy == "chunks" and name in ("coalesced", "reordered", "missing_deliveries", "fabricated_exhaustion"):
                    self.assertEqual(view["relation_gaps"], [{"id": "deliveries", "reason": "MISSING" if name == "missing_deliveries" else "MISMATCH"}])
        baseline, candidate = read(EX / "fixed-buffer.json"), read(EX / "fixed-chunks.json")
        self.assertEqual(candidate["relations"][:-1], baseline["relations"])
        self.assertEqual(candidate["relations"][-1]["id"], "deliveries")
        self.assertEqual(baseline["relations"][:-1], read(ROOT / "examples/parser_input/fixed-raw.json")["relations"])

    def test_capture_tracks_actual_pulls_objects_and_early_failure(self):
        probe = load_probe()
        captured = []
        identity = probe.byte_identity
        def capture(chunk):
            captured.append(chunk)
            return identity(chunk)
        probe.byte_identity = capture
        chunks = [b"first", b"second", b"third"]
        stream = probe.DeliveredChunks(chunks)
        self.assertEqual(stream.trace, [])
        self.assertIs(next(stream), chunks[0])
        self.assertIs(captured[-1], chunks[0])
        self.assertEqual(len(stream.trace), 1)
        self.assertFalse(stream.exhausted)
        next(stream); next(stream)
        self.assertFalse(stream.exhausted)
        with self.assertRaises(StopIteration): next(stream)
        self.assertTrue(stream.exhausted)
        case = next(c for c in read(EX / "manifest.json")["cases"] if c["id"] == "repeat_fragments")
        received = []
        class Sentinel:
            def __init__(self, stream): self.stream = stream
            def events(self):
                for _ in range(2):
                    chunk = next(self.stream)
                    self_case.assertIs(chunk, captured[-1])
                    received.append(chunk)
                raise ValueError("early consumer failure")
        class Module: SSEClient = Sentinel
        self_case = self
        observed = probe.observe(Module, case, EX / "inputs", "reorder")
        self.assertEqual(received, [b"data: ", b"AA"])
        self.assertEqual(observed["delivery"], {"chunks": list(map(identity, received)), "exhausted": False})
        self.assertEqual(observed["buffer"], identity(b"data: AA"))
        self.assertEqual(observed["actual"], {"events": [], "error_kind": "ValueError"})
        self.assertEqual(observed["error"], "early consumer failure")

    def test_documented_commands(self):
        commands = re.findall(r"^python tools/read_requirements.py .+$", (ROOT / "docs/stream-chunk-evaluation.md").read_text(encoding="utf-8"), re.M)
        self.assertEqual(len(commands), 10)
        for command, code in zip(commands, (1, 1, 0, 0, 0, 1, 0, 1, 1, 1)):
            args = shlex.split(command); args[0] = sys.executable
            run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            self.assertEqual(json.loads(run.stdout)["status"], "INSUFFICIENT" if code else "OBSERVED")

    def test_probe_rejects_invalid_inputs_before_target(self):
        probe = load_probe()
        manifest, oracle = read(EX / "manifest.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        with self.assertRaises(ValueError): probe.read_pinned(EX / "manifest.json", "0" * 64)
        for kind in ("path", "boolean_cut", "duplicate_cut", "negative_cut", "schema", "duplicate_id", "oracle"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "path": m["cases"][0]["file"] = "../escape.bin"
            elif kind == "boolean_cut": m["cases"][0]["cuts"] = [True]
            elif kind == "duplicate_cut": m["cases"][0]["cuts"] = [1, 1]
            elif kind == "negative_cut": m["cases"][0]["cuts"] = [-1]
            elif kind == "schema": m["schema_version"] = True
            elif kind == "duplicate_id": m["cases"][1]["id"] = m["cases"][0]["id"]
            else: del o["expected"]["empty"]
            with self.assertRaises(ValueError): probe.validate(m, o)
        case = dict(manifest["cases"][0], cuts=[4095])
        with self.assertRaises(ValueError): probe.observe(None, case, EX / "inputs", "declared")
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "pin.json"; p.write_bytes(b'{"a":1,"a":2}')
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))
            p.write_bytes(b"x" * 65537)
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))


if __name__ == "__main__":
    unittest.main()
