"""Check saved file-effect evidence and executable source-only examples."""
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
EX = ROOT / "examples/artifact_effects"
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def probe_module():
    spec = importlib.util.spec_from_file_location("artifact_effects_probe", EX / "probe.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class ArtifactEffectsExample(unittest.TestCase):
    def test_pins_and_literal_artifact_outcomes(self):
        report, contract = read(EX / "results.json"), read(EX / "contract.json")
        oracle = read(EX / "oracle.json")["expected"]
        inputs = {c["id"]: c for c in read(EX / "manifest.json")["cases"]}
        self.assertEqual(sha(EX / "probe.py"), report["probe_sha256"])
        self.assertEqual(set(report["variants"]), set(contract["variants"]))
        for name, digest in report["input_sha256"].items():
            self.assertEqual(sha(EX / name), digest)
            raw = (EX / name).read_bytes()
            self.assertEqual(canonical_release_bytes("examples/artifact_effects/" + name, raw), raw)
        for name, actual in report["variants"].items():
            self.assertEqual(len(actual["tests"]), 12)
            self.assertEqual({t["id"] for t in actual["tests"]}, set(oracle))
            failed = set(contract["case_ids"][:4]) if name == "original" else set(contract["case_ids"][-2:]) if name == "inplace" else set()
            for t in actual["tests"]:
                expected = oracle[t["id"]]
                self.assertEqual((t["return"], t["exception"]), (expected["return"], expected["exception"]))
                self.assertEqual(t["before"], inputs[t["id"]]["before"])
                self.assertEqual(t["outcome_status"], "PASS")
                self.assertEqual(t["temp_files"], [])
                self.assertEqual(t["before_sha256"], hashlib.sha256(t["before"].encode()).hexdigest())
                self.assertEqual(t["after_sha256"], hashlib.sha256(t["after"].encode()).hexdigest())
                wanted = expected["after_windows" if actual["runtime"]["platform"] == "win32" else "after_posix"]
                self.assertEqual(t["after"] == wanted, t["id"] not in failed)
                self.assertEqual(t["status"], "FAIL" if t["id"] in failed else "PASS")
                self.assertEqual(t["artifact_status"], t["status"])
                self.assertEqual(t["fault_hits"], ["after_first_binding"] if t["id"].startswith("recovery_") else [])
            self.assertTrue(actual["canary_unchanged"])
            self.assertFalse(actual["crash_durability_tested"])
        for name in ("original", "fixed", "inplace"):
            receipt = read(EX / (name + "-source.json"))["observations"][1]["value"]
            self.assertEqual(receipt["artifact_passed_ids"], [t["id"] for t in receipt["tests"] if t["artifact_status"] == "PASS"])
            self.assertEqual(receipt["outcome_passed_ids"], contract["case_ids"])

    def test_documented_commands_and_preserved_observations(self):
        doc = (ROOT / "docs/artifact-effects-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 6)
        for line, code in zip(commands, (0, 1, 0, 0, 0, 1)):
            args = shlex.split(line)
            args[0] = sys.executable
            result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            view = json.loads(result.stdout)
            if code:
                self.assertEqual(view["relation_gaps"], [{"id": "artifact-effects", "reason": "MISMATCH"}])
                self.assertNotIn("requirements", view)
            else:
                source = read(ROOT / args[args.index("--source") + 1])
                self.assertEqual([o for row in view["requirements"] for o in row["observations"]], source["observations"])

    def test_missing_artifact_evidence_is_not_partial_success(self):
        source = read(EX / "fixed-source.json")
        del source["observations"][1]["value"]["artifact_passed_ids"]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "source.json").write_bytes(E.encode(source))
            question = read(EX / "fixed-complete.json")
            question["source_sha256"] = sha(folder / "source.json")
            (folder / "question.json").write_bytes(E.encode(question))
            view = R.read_requirements(folder / "question.json", sha(folder / "question.json"), folder / "source.json")
            self.assertEqual(view["status"], "INSUFFICIENT")
            self.assertEqual(view["relation_gaps"], [{"id": "artifact-effects", "reason": "MISSING"}])
            self.assertNotIn("requirements", view)

    def test_probe_refuses_unreviewed_cases_and_existing_scratch(self):
        probe = probe_module()
        manifest, oracle = read(EX / "manifest.json"), read(EX / "oracle.json")
        probe.validate(manifest, oracle)
        with self.assertRaises(ValueError):
            probe.read_pinned(EX / "manifest.json", "0" * 64)
        for change in ("traversal", "duplicate", "unknown_fault", "missing_setting", "missing_oracle"):
            m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
            if change == "traversal":
                m["cases"][0]["id"] = "../outside"
            elif change == "duplicate":
                m["cases"][1]["id"] = m["cases"][0]["id"]
            elif change == "unknown_fault":
                m["cases"][0]["fault"] = "after_commit"
            elif change == "missing_setting":
                del m["cases"][0]["quote_mode"]
            else:
                del o["expected"][m["cases"][0]["id"]]
            with self.assertRaises(ValueError):
                probe.validate(m, o)
        with tempfile.TemporaryDirectory() as folder, patch.object(probe, "capture_scope", return_value={}):
            folder = Path(folder)
            keep = folder / "existing.txt"
            keep.write_bytes(b"preserve")
            with self.assertRaises(ValueError):
                probe.run(folder, manifest, oracle, folder)
            self.assertEqual(keep.read_bytes(), b"preserve")
            self.assertEqual(list(folder.iterdir()), [keep])

    def test_fault_hook_restores_parser_and_temp_settings(self):
        probe = probe_module()
        manifest, oracle = read(EX / "manifest.json"), read(EX / "oracle.json")
        case = manifest["cases"][-1]
        class Module:
            @staticmethod
            def parse_stream(stream):
                yield object()
                yield object()

            @staticmethod
            def set_key(path, *args, **kwargs):
                list(Module.parse_stream(None))
                raise AssertionError("fault hook did not run")
        original_parser = Module.parse_stream
        with tempfile.TemporaryDirectory() as folder:
            original_temp = tempfile.tempdir
            row = probe.run_case(Module, case, oracle["expected"][case["id"]], Path(folder))
            self.assertEqual(row["status"], "PASS")
            self.assertEqual(row["before"], row["after"])
            self.assertEqual(row["fault_hits"], ["after_first_binding"])
            self.assertEqual(tempfile.tempdir, original_temp)
        self.assertIs(Module.parse_stream, original_parser)


if __name__ == "__main__":
    unittest.main()
