"""Validate saved configuration receipts without downloading external code."""
import copy
import hashlib
import importlib.util
import json
import os
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
EXAMPLE = ROOT / "examples/dotenv_task"
read = lambda p: json.loads(p.read_bytes())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def load_probe():
    spec = importlib.util.spec_from_file_location("configuration_example_probe", EXAMPLE / "probe.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class ConfigurationScopeExample(unittest.TestCase):
    def test_frozen_inputs_and_all_actual_outcomes(self):
        report = read(EXAMPLE / "results.json")
        contract = read(EXAMPLE / "contract.json")
        oracle = read(EXAMPLE / "oracle.json")["expected"]
        self.assertEqual(digest(EXAMPLE / "probe.py"), report["probe_sha256"])
        for name, expected in report["input_sha256"].items():
            self.assertEqual(digest(EXAMPLE / name), expected, name)
            raw = (EXAMPLE / name).read_bytes()
            self.assertEqual(canonical_release_bytes("examples/dotenv_task/" + name, raw), raw)
        repair = read(EXAMPLE / "format-repair.json")
        self.assertEqual(repair["repaired_frozen_sha256"], report["frozen_sha256"])
        for name, pins in repair["repairs"].items():
            raw = (EXAMPLE / name).read_bytes()
            original = raw.replace(b"\n", b"\r\n")
            self.assertEqual(hashlib.sha256(original).hexdigest(), pins["original"])
            self.assertEqual(digest(EXAMPLE / name), pins["canonical"])
            self.assertEqual(json.loads(original), json.loads(raw))
        self.assertEqual(len(oracle), 12)
        self.assertEqual(set(report["variants"]), set(contract["variants"]))
        for name, actual in report["variants"].items():
            with self.subTest(variant=name):
                self.assertEqual({row["id"] for row in actual["tests"]}, set(oracle))
                fail_ids = set(contract["repair_ids"]) if name in ("original", "wrong-mode", "wrong-environment") else {"preserve_unicode"} if name == "wrong-input" else set()
                for row in actual["tests"]:
                    self.assertEqual(row["status"], "FAIL" if row["id"] in fail_ids else "PASS")
                    self.assertEqual(row["actual"] == oracle[row["id"]], row["status"] == "PASS")
                    self.assertIs(type(row["actual"]["return"]), bool)
                    self.assertTrue(all(key.startswith("X35_") for key in row["actual"]["environment"]))
                manifest = contract["variants"][name]["manifest"]
                self.assertEqual(actual["manifest_sha256"], digest(EXAMPLE / manifest))
                if name != "original":
                    self.assertEqual(actual["code_scope"], report["variants"]["fixed"]["code_scope"])
        for subset in report["upstream_subsets"].values():
            self.assertEqual((subset["tests"], subset["exit_code"], subset["full_suite"]), (49, 0, False))

    def test_documented_commands_preserve_facts_and_reject_wrong_mode_replay(self):
        doc = (ROOT / "docs/configuration-scope-evaluation.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirements.py .+$", doc, re.M)
        self.assertEqual(len(commands), 4)
        for index, (line, code) in enumerate(zip(commands, (0, 1, 0, 0))):
            with self.subTest(command=index):
                args = shlex.split(line)
                args[0] = sys.executable
                run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=10)
                self.assertEqual(run.returncode, code, run.stdout + run.stderr)
                result = json.loads(run.stdout)
                if code:
                    self.assertEqual(result["relation_gaps"], [{"id": "execution-manifest", "reason": "MISMATCH"}])
                    self.assertNotIn("requirements", result)
                else:
                    source = read(ROOT / args[args.index("--source") + 1])
                    self.assertEqual([o for row in result["requirements"] for o in row["observations"]], source["observations"])

    def test_input_and_environment_replays_are_rejected_without_partial_views(self):
        original = read(EXAMPLE / "fixed-source.json")
        report = read(EXAMPLE / "results.json")
        for variant in ("wrong-input", "wrong-environment", "equivalent-input"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                source = copy.deepcopy(original)
                proposal, receipt = [row["value"] for row in source["observations"][:2]]
                proposal["manifest_sha256"] = report["variants"][variant]["manifest_sha256"]
                if variant == "equivalent-input":
                    receipt["manifest_sha256"] = proposal["manifest_sha256"]
                    receipt["tests"] = report["variants"][variant]["tests"]
                folder = Path(tmp)
                (folder / "source.json").write_bytes(E.encode(source))
                question = read(EXAMPLE / "fixed-complete.json")
                question["source_sha256"] = digest(folder / "source.json")
                (folder / "question.json").write_bytes(E.encode(question))
                result = R.read_requirements(folder / "question.json", digest(folder / "question.json"), folder / "source.json")
                if variant == "equivalent-input":
                    self.assertEqual(result["status"], "OBSERVED")
                    self.assertEqual([o for row in result["requirements"] for o in row["observations"]], source["observations"])
                else:
                    self.assertEqual(result["relation_gaps"], [{"id": "execution-manifest", "reason": "MISMATCH"}])
                    self.assertNotIn("requirements", result)

    def test_fixture_guards_reject_wrong_pins_ids_and_modes(self):
        probe = load_probe()
        manifest, oracle = read(EXAMPLE / "manifest.json"), read(EXAMPLE / "oracle.json")
        probe.validate(manifest, oracle)
        with self.assertRaises(ValueError):
            probe.read_pinned(EXAMPLE / "manifest.json", "0" * 64)
        for control in ("duplicate", "missing-mode", "integer-mode", "unknown-mode", "host-key", "missing-oracle"):
            with self.subTest(control=control):
                m, o = copy.deepcopy(manifest), copy.deepcopy(oracle)
                if control == "duplicate":
                    m["cases"][1]["id"] = m["cases"][0]["id"]
                elif control == "missing-mode":
                    del m["cases"][0]["override"]
                elif control == "integer-mode":
                    m["cases"][0]["override"] = 0
                elif control == "unknown-mode":
                    m["cases"][0]["inherit_host"] = True
                elif control == "host-key":
                    m["cases"][0]["environment"] = {"UNREVIEWED_KEY": "synthetic"}
                else:
                    del o["expected"][m["cases"][0]["id"]]
                with self.assertRaises(ValueError):
                    probe.validate(m, o)

    def test_process_environment_is_isolated_and_restored_on_success_or_error(self):
        probe = load_probe()
        case = read(EXAMPLE / "manifest.json")["cases"][0]
        manifest = {"schema_version": 1, "cases": [case]}
        oracle = {"schema_version": 1, "expected": {case["id"]: read(EXAMPLE / "oracle.json")["expected"][case["id"]]}}
        for fail in (False, True):
            with self.subTest(fail=fail), patch.dict(os.environ, {"TEST_HOST_CANARY": "must-stay-private"}):
                before = dict(os.environ)
                def fake_load(**kwargs):
                    self.assertEqual(dict(os.environ), case["environment"])
                    self.assertEqual(kwargs["stream"].read(), case["dotenv"])
                    self.assertEqual((kwargs["override"], kwargs["interpolate"]), (False, True))
                    if fail:
                        raise RuntimeError("controlled failure")
                    os.environ["X35_URL"] = "environment"
                    return True
                rows = probe.run_cases(fake_load, manifest, oracle)
                self.assertEqual(dict(os.environ), before)
                self.assertEqual(rows[0]["status"], "ERROR" if fail else "PASS")
                self.assertNotIn("TEST_HOST_CANARY", json.dumps(rows))
                self.assertNotIn("must-stay-private", json.dumps(rows))


if __name__ == "__main__":
    unittest.main()
