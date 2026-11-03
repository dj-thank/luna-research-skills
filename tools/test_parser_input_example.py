"""Check frozen parser-boundary evidence without importing external TOML."""
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
EX = ROOT / "examples/parser_input"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_probe():
    spec = importlib.util.spec_from_file_location("parser_input_probe", EX / "probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParserInputExample(unittest.TestCase):
    def test_pins_and_independent_known_answers(self):
        result, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        self.assertEqual(oracle["quote_both"], {"value": {"test": '"one"'}, "error_kind": None})
        self.assertEqual(oracle["quote_japanese"], {"value": {"test": '"日本"'}, "error_kind": None})
        self.assertEqual(contract["expected_parser_inputs"]["quote_both"]["text"], 'test = "\\"one\\""\n')
        self.assertEqual(contract["expected_parser_inputs"]["numbers_crlf"]["text"], "n = 7\nflag = true\n")
        for name, field in (("probe.py", "probe_sha256"), ("manifest.json", "manifest_sha256"), ("oracle.json", "oracle_sha256"), ("accepted.patch", "patch_sha256")):
            self.assertEqual(sha(EX / name), result[field])
        self.assertEqual({p.name: sha(p) for p in (EX / "inputs").iterdir()}, result["input_sha256"])
        for name, pin in result["snapshot_manifest_sha256"].items():
            self.assertEqual(sha(EX / (name + "-source-manifest.json")), pin)
        manifest = {c["id"]: c for c in read(EX / "manifest.json")["cases"]}
        for variant, report in result["variants"].items():
            settings = contract["variants"][variant]
            self.assertEqual(report["code_scope"], contract["code_scopes"][settings["code"]])
            self.assertEqual(report["mode"], settings["mode"])
            self.assertEqual([r["id"] for r in report["tests"]], contract["case_ids"])
            self.assertEqual(report["actual_inputs"], contract["expected_inputs"])
            for row in report["tests"]:
                case = manifest[row["id"]]
                raw = (EX / "inputs" / case["file"]).read_bytes()
                self.assertEqual(row["input"], {"path": case["file"], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
                text = case["control_text"] if variant == "rewritten" and case["control_text"] is not None else contract["expected_parser_inputs"][row["id"]]["text"]
                self.assertEqual(row["parser_input"], {"type": "str", "characters": len(text), "utf8_bytes": len(text.encode("utf-8")), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "text": text})
                self.assertEqual(row["status"], "PASS" if encode(row["actual"]) == encode(oracle[row["id"]]) else "FAIL")
                self.assertEqual(row["actual"], report["actual_outputs"][row["id"]])
                self.assertEqual(row["parser_input"], report["actual_parser_inputs"][row["id"]])
            self.assertEqual([row["id"] for row in report["tests"] if row["status"] == "FAIL"], settings["failed_ids"])
            self.assertEqual([row["id"] for row in report["tests"] if row["parser_input"] != contract["expected_parser_inputs"][row["id"]]], settings["parser_mismatch_ids"])
            self.assertEqual(read(EX / (variant + "-source.json"))["observations"][1]["value"], report)
        variants = result["variants"]
        self.assertEqual(variants["base"]["code_scope"], variants["rewritten"]["code_scope"])
        self.assertEqual(variants["fixed"]["actual_outputs"], variants["rewritten"]["actual_outputs"])
        for case in ("quote_japanese", "numbers_crlf"):
            self.assertIn(b"\r\n", (EX / "inputs" / manifest[case]["file"]).read_bytes())
            self.assertNotIn("\r", contract["expected_parser_inputs"][case]["text"])
            self.assertNotEqual(contract["expected_inputs"][case]["sha256"], contract["expected_parser_inputs"][case]["sha256"])

    def test_documented_decisions_preserve_all_evidence(self):
        commands = re.findall(r"^python tools/read_requirements.py .+$", (ROOT / "docs/parser-input-evaluation.md").read_text(encoding="utf-8"), re.M)
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
        previous = read(ROOT / "examples/json_input_transfer/fixed-inputs.json")
        raw, stronger = read(EX / "fixed-raw.json"), read(EX / "fixed-parser.json")
        self.assertEqual(raw["relations"], previous["relations"])
        self.assertEqual(stronger["relations"][:-1], raw["relations"])
        self.assertEqual(stronger["relations"][-1]["id"], "parser_inputs")

    def test_missing_and_same_value_swapped_parser_inputs(self):
        fixed = read(EX / "fixed-source.json")["observations"][1]["value"]
        self.assertEqual(fixed["actual_outputs"]["quote_both"], fixed["actual_outputs"]["literal_equivalent"])
        for name, reason in (("missing_parser_inputs", "MISSING"), ("case_mapping_swapped", "MISMATCH")):
            receipt = read(EX / (name + "-source.json"))["observations"][1]["value"]
            self.assertEqual(receipt["actual_outputs"], fixed["actual_outputs"])
            self.assertEqual(receipt["actual_inputs"], fixed["actual_inputs"])
            if name == "case_mapping_swapped":
                bag = lambda mapping: collections.Counter(encode(value) for value in mapping.values())
                self.assertEqual(bag(receipt["actual_parser_inputs"]), bag(fixed["actual_parser_inputs"]))
            for policy, status in (("raw", "OBSERVED"), ("parser", "INSUFFICIENT")):
                q = EX / (name + "-" + policy + ".json")
                view = R.read_requirements(q, sha(q), EX / (name + "-source.json"))
                self.assertEqual(view["status"], status)
                if policy == "parser":
                    self.assertEqual(view["relation_gaps"], [{"id": "parser_inputs", "reason": reason}])
                    self.assertNotIn("requirements", view)

    def test_capture_is_after_preprocessing_at_actual_call(self):
        probe = load_probe()
        cases = {c["id"]: c for c in read(EX / "manifest.json")["cases"]}
        captured = []
        identity = probe.parser_identity
        def capture(payload):
            captured.append(payload)
            return identity(payload)
        probe.parser_identity = capture
        class Sentinel:
            fail = False
            def loads(self, payload):
                self.payload = payload
                if self.fail:
                    raise ValueError("sentinel parser failure")
                return {"sentinel": True}
        sentinel = Sentinel()
        for case, mode, expected in (
            ("quote_japanese", "declared", 'test = "\\"日本\\""\n'),
            ("quote_japanese", "rewrite_quotes", "test = '\"日本\"'\n"),
            ("numbers_crlf", "declared", "n = 7\nflag = true\n"),
        ):
            for fail in (False, True):
                sentinel.fail = fail
                actual, raw, parsed, error = probe.observe(sentinel, cases[case], EX / "inputs", mode)
                self.assertIs(sentinel.payload, captured[-1])
                self.assertEqual(sentinel.payload, expected)
                self.assertEqual(parsed["text"], expected)
                self.assertEqual(raw["sha256"], sha(EX / "inputs" / cases[case]["file"]))
                self.assertEqual(actual["error_kind"], "ValueError" if fail else None)
                self.assertEqual(error, "sentinel parser failure" if fail else None)

    def test_probe_rejects_invalid_manifest_and_pins(self):
        probe = load_probe()
        manifest, oracle = read(EX / "manifest.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        self.assertNotEqual(probe.canonical({"value": True}), probe.canonical({"value": 1}))
        with self.assertRaises(ValueError): probe.read_pinned(EX / "manifest.json", "0" * 64)
        for kind in ("path", "preprocess", "control", "duplicate", "schema", "count", "oracle", "error"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if kind == "path": m["cases"][0]["file"] = "../escape.bin"
            elif kind == "preprocess": m["cases"][0]["preprocess"] = "strip_quotes"
            elif kind == "control": m["cases"][0]["control_text"] = "x" * 4097
            elif kind == "duplicate": m["cases"][1]["id"] = m["cases"][0]["id"]
            elif kind == "schema": m["schema_version"] = True
            elif kind == "count": m["cases"] *= 2
            elif kind == "oracle": del o["expected"]["empty"]
            else: o["expected"]["reserved_escape"]["value"] = 1
            with self.assertRaises(ValueError): probe.validate(m, o)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "large.json"; p.write_bytes(b"x" * 65537)
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))
            p.write_bytes(b'{"a":1,"a":2}')
            with self.assertRaises(ValueError): probe.read_pinned(p, sha(p))


if __name__ == "__main__":
    unittest.main()
