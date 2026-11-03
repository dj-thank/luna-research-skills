import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

import read_evidence as E
import read_requirement_sources as C


class ReadRequirementSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixtures = Path(__file__).with_name("fixtures")
        self.docs = {s: E.load_json((fixtures / ("cross_" + filename + ".json")).read_bytes())
                     for s, filename in (("sender", "sender"), ("registry", "registry"))}
        self.question = E.load_json((fixtures / "cross_question.json").read_bytes())
        self.path = self.root / "question.json"

    def write(self, raw_registry=None):
        for s, doc in self.docs.items():
            raw = raw_registry if s == "registry" and raw_registry is not None else E.encode(doc)
            (self.root / (s + ".json")).write_bytes(raw)
            next(row for row in self.question["sources"] if row["id"] == s)["sha256"] = E.digest(raw)
        self.path.write_bytes(E.encode(self.question))
        return [(s["id"], self.root / (s["id"] + ".json")) for s in self.question["sources"]]

    def run_case(self, raw_registry=None):
        bindings = self.write(raw_registry)
        return C.read_sources(self.path, E.digest(self.path.read_bytes()), bindings)

    def no_partial(self, report, status):
        self.assertEqual(report["status"], status, report)
        self.assertNotIn("requirements", report)
        self.assertNotIn("observations", report)

    def test_complete_view_preserves_source_identity_and_original_records(self):
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertEqual(report["metrics"]["source_reads"], 2)
        self.assertEqual(report["metrics"]["source_bytes_read"],
                         sum((self.root / (s + ".json")).stat().st_size for s in self.docs))
        for requirement in report["requirements"]:
            self.assertEqual(len(requirement["observations"]), 2)
            for obs in requirement["observations"]:
                sid = obs["origin"]["id"]
                original = next(r for r in self.docs[sid]["observations"] if r["id"] == obs["id"])
                self.assertEqual(E.encode({k:v for k,v in obs.items() if k != "origin"}), E.encode(original))
                self.assertEqual(obs["origin"]["sha256"], E.digest((self.root / (sid + ".json")).read_bytes()))

    def test_complementary_requirements_name_their_actual_sources(self):
        self.question["requirements"][0]["sources"] = ["sender"]
        self.question["requirements"][1]["sources"] = ["registry"]
        self.docs["sender"]["observations"].pop(1)
        self.docs["registry"]["observations"].pop(0)
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertEqual([len(r["observations"]) for r in report["requirements"]], [1, 1, 2])

    def test_conflict_does_not_choose_first_newest_or_majority_record(self):
        self.docs["registry"]["observations"][1]["value"] = "approved"
        sender = self.docs["sender"]["observations"]
        sender.extend(dict(copy.deepcopy(sender[1]), id="repeat-" + str(i)) for i in range(3))
        for reverse in (False, True):
            if reverse:
                self.question["sources"].reverse()
                for req in self.question["requirements"]:
                    req["sources"].reverse()
            report = self.run_case()
            self.no_partial(report, "INSUFFICIENT")
            self.assertEqual(report["gaps"], [{"id":"authorization", "reason":"CONFLICT"}])

    def test_unknown_precedes_conflict_after_source_coverage(self):
        self.docs["registry"]["observations"].append(
            dict(copy.deepcopy(self.docs["registry"]["observations"][1]), id="unknown", state="unknown", value=None))
        self.docs["registry"]["observations"][1]["value"] = "approved"
        report = self.run_case()
        self.no_partial(report, "INSUFFICIENT")
        self.assertEqual(report["gaps"], [{"id":"authorization", "reason":"UNKNOWN"}])

    def test_missing_source_record_cannot_be_substituted_by_another_subject(self):
        self.docs["registry"]["observations"][0]["subject"] = "release-80"
        report = self.run_case()
        self.no_partial(report, "INSUFFICIENT")
        self.assertEqual(report["gaps"], [{"id":"artifact", "reason":"MISSING_SOURCE", "sources":["registry"]}])

    def test_negative_values_and_prose_qualifiers_are_retained(self):
        for s in self.docs:
            self.docs[s]["observations"][1]["value"] = False
            self.docs[s]["observations"][1]["qualifiers"] += ["Contradictory prose from " + s]
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        values = report["requirements"][1]["observations"]
        self.assertTrue(all(obs["value"] is False for obs in values))
        self.assertNotEqual(values[0]["qualifiers"], values[1]["qualifiers"])

    def test_typed_values_and_array_order_are_not_collapsed(self):
        for left, right in ((False, 0), (1, 1.0), (["a", "b"], ["b", "a"])):
            for s,v in (("sender",left),("registry",right)):
                self.docs[s]["observations"][1]["value"] = v
            report = self.run_case()
            self.no_partial(report, "INSUFFICIENT")
            self.assertEqual(report["gaps"], [{"id":"authorization", "reason":"CONFLICT"}])

    def test_explicit_bindings_reject_omission_extra_and_duplicate_before_reads(self):
        pairs = self.write()
        for bindings in (pairs[:-1], pairs + [pairs[0]], pairs + [("unexpected", self.root/"registry.json")]):
            report = C.read_sources(self.path, E.digest(self.path.read_bytes()), bindings)
            self.no_partial(report, "REFUSED")
            self.assertEqual(report["metrics"]["source_reads"], 0)

    def test_question_pin_fails_before_any_source_is_read(self):
        pairs = self.write()
        report = C.read_sources(self.path, "0"*64, pairs)
        self.no_partial(report, "REFUSED")
        self.assertEqual(report["metrics"]["source_reads"], 0)

    def test_second_source_pin_failure_exposes_no_partial_source_claim(self):
        pairs = self.write()
        (self.root/"registry.json").write_bytes(b"{}")
        report = C.read_sources(self.path, E.digest(self.path.read_bytes()), pairs)
        self.no_partial(report, "REFUSED")
        self.assertNotIn("sources", report)
        self.assertEqual(report["metrics"]["source_reads"], 2)

    def test_aggregate_read_budget_is_not_applied_independently_per_file(self):
        self.write()
        total = sum((self.root/(s+".json")).stat().st_size for s in self.docs)
        self.question["max_source_bytes"] = total-1
        report = self.run_case()
        self.no_partial(report, "REFUSED")
        self.assertLessEqual(report["metrics"]["source_bytes_read"], self.question["max_source_bytes"]+1)

    def test_successful_result_limit_includes_all_metadata_and_newline(self):
        report = self.run_case()
        exact = len(E.encode(report))
        self.question["max_result_bytes"] = exact
        self.assertEqual(self.run_case()["status"], "OBSERVED")
        self.question["max_result_bytes"] = exact-1
        self.no_partial(self.run_case(), "REFUSED")

    def test_all_records_are_validated_even_if_not_selected(self):
        self.docs["registry"]["observations"].append(
            dict(copy.deepcopy(self.docs["registry"]["observations"][0]), id="irrelevant",
                 subject="other", origin={"id":"forged"}))
        self.no_partial(self.run_case(), "REFUSED")

    def test_same_record_ids_across_sources_are_valid_but_repeated_ids_within_one_are_not(self):
        self.assertEqual(self.run_case()["status"], "OBSERVED")
        self.docs["registry"]["observations"].append(copy.deepcopy(self.docs["registry"]["observations"][0]))
        self.no_partial(self.run_case(), "REFUSED")

    def test_invalid_question_contracts_fail_before_sources(self):
        original = copy.deepcopy(self.question)
        mutations = [
            lambda q:q.update(schema_version=True), lambda q:q.update(max_source_bytes=True),
            lambda q:q.update(sources=q["sources"][:1]),
            lambda q:q["sources"].append(copy.deepcopy(q["sources"][0])),
            lambda q:q["requirements"][0].update(sources=["absent"]),
            lambda q:q["requirements"][0].update(sources=["sender","sender"]),
            lambda q:q["requirements"][0].update(sources=[]),
            lambda q:q.update(requirements=[dict(r,sources=["sender"]) for r in q["requirements"]]),
            lambda q:q["requirements"].append(copy.deepcopy(q["requirements"][0])),
            lambda q:q["sources"][0].update(path="do-not-follow"),
        ]
        for mutation in mutations:
            self.question = copy.deepcopy(original)
            pairs = self.write()
            mutation(self.question)
            self.path.write_bytes(E.encode(self.question))
            result = C.read_sources(self.path, E.digest(self.path.read_bytes()), pairs)
            self.no_partial(result, "REFUSED")
            self.assertEqual(result["metrics"]["source_reads"], 0)

    def test_malformed_and_lossy_json_is_refused(self):
        for raw in (b'{"schema_version":1,"schema_version":1,"observations":[]}',
                    b'{"schema_version":1,"observations":[NaN]}',
                    b'{"number":0.1234567890123456789012345}'):
            self.no_partial(self.run_case(raw_registry=raw), "REFUSED")

    def test_nonregular_or_missing_source_returns_refusal(self):
        pairs = self.write()
        for path in (self.root, self.root/"absent.json"):
            result = C.read_sources(self.path, E.digest(self.path.read_bytes()), [pairs[0],("registry",path)])
            self.no_partial(result, "REFUSED")

    def test_cli_is_read_only_even_when_environment_flags_are_ignored(self):
        pairs = self.write()
        for name in ("read_requirement_sources.py","read_requirements.py","read_evidence.py"):
            shutil.copyfile(Path(__file__).with_name(name), self.root/name)
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        command = [sys.executable,"-E",str(self.root/"read_requirement_sources.py"),
                   "--question",str(self.path),"--sha256",E.digest(self.path.read_bytes())]
        for sid,path in pairs:
            command.extend(["--source",sid,str(path)])
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["status"], "OBSERVED")
        self.assertEqual(before, {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_documented_examples(self):
        repo = Path(__file__).resolve().parents[1]
        doc = (repo/"docs/cross-source-requirements.md").read_text(encoding="utf-8")
        commands = re.findall(r"^python tools/read_requirement_sources.py .+$", doc, re.M)
        self.assertEqual(len(commands), 2)
        for code, line in enumerate(commands):
            command = shlex.split(line); command[0] = sys.executable
            run = subprocess.run(command,cwd=repo,capture_output=True,text=True,encoding="utf-8",timeout=10)
            self.assertEqual(run.returncode,code,run.stdout+run.stderr)
            self.assertEqual(json.loads(run.stdout)["status"], "OBSERVED" if code==0 else "INSUFFICIENT")


if __name__ == "__main__":
    unittest.main()
