import copy
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import read_evidence as E
import read_requirement_sources as C


class TemporalRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        fixture = Path(__file__).with_name("fixtures")
        self.q = E.load_json((fixture / "temporal_question.json").read_bytes())
        self.docs = {s: E.load_json((fixture / ("temporal_" + s + ".json")).read_bytes())
                     for s in ("sender", "register")}

    def write(self):
        for sid, doc in self.docs.items():
            raw = E.encode(doc)
            (self.root / (sid + ".json")).write_bytes(raw)
            next(s for s in self.q["sources"] if s["id"] == sid)["sha256"] = E.digest(raw)
        raw = E.encode(self.q)
        (self.root / "q.json").write_bytes(raw)
        return self.root / "q.json", E.digest(raw), [(s, self.root / (s + ".json")) for s in self.docs]

    def run_case(self):
        return C.read_sources(*self.write())

    def mutate_value(self, callback, index=0):
        for doc in self.docs.values():
            callback(doc["observations"][index]["value"])

    def gap(self, report, reason, requirement="snapshot"):
        self.assertEqual(report["status"], "INSUFFICIENT", report)
        self.assertNotIn("requirements", report)
        self.assertEqual(report["time_gaps"], [
            dict(id=requirement + "-window", requirement=requirement, reason=reason)])

    def test_complete_preserves_all_observations_and_origins(self):
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertEqual(report["as_of"], self.q["as_of"])
        self.assertEqual(report["scope"], "declared_requirements_sources_and_time_only")
        self.assertEqual(len(report["time_checks"]), 2)
        for req in report["requirements"]:
            for obs in req["observations"]:
                sid = obs["origin"]["id"]
                original = next(o for o in self.docs[sid]["observations"] if o["id"] == obs["id"])
                self.assertEqual({k:v for k,v in obs.items() if k != "origin"}, original)

    def test_half_open_boundaries(self):
        self.q["as_of"] = "2031-06-15T11:00:00Z"
        self.assertEqual(self.run_case()["status"], "OBSERVED")
        self.q["as_of"] = "2031-06-15T12:59:59Z"
        self.assertEqual(self.run_case()["status"], "OBSERVED")
        self.mutate_value(lambda v: v.update(valid_until=self.q["as_of"]))
        self.gap(self.run_case(), "EXPIRED")

    def test_future_is_not_accepted(self):
        self.mutate_value(lambda v: v.update(valid_from="2031-06-15T12:00:01Z"))
        self.gap(self.run_case(), "NOT_YET_VALID")

    def test_historical_negative_answer_is_not_replaced_by_now(self):
        self.q["as_of"] = "2000-01-01T00:00:00Z"
        for index in (0, 1):
            self.mutate_value(lambda v: v.update(valid_from="1999-12-31T00:00:00Z",
                                                valid_until="2000-01-02T00:00:00Z", fact=False), index)
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertIs(report["requirements"][1]["observations"][0]["value"]["fact"], False)

    def test_real_calendar_handles_leap_day(self):
        self.q["as_of"] = "2032-02-29T12:00:00Z"
        for index in (0, 1):
            self.mutate_value(lambda v: v.update(valid_from="2032-02-29T00:00:00Z",
                                                valid_until="2032-03-01T00:00:00Z"), index)
        self.assertEqual(self.run_case()["status"], "OBSERVED")

    def test_unknown_end_is_not_open_ended_validity(self):
        self.mutate_value(lambda v: v.update(valid_until=None))
        self.gap(self.run_case(), "UNKNOWN")

    def test_missing_time_does_not_fall_back_to_other_field(self):
        self.mutate_value(lambda v: v.pop("valid_from"))
        self.gap(self.run_case(), "MISSING")

    def test_bad_types_calendar_offsets_and_precision(self):
        original = copy.deepcopy(self.docs)
        for value in (True, 0, [], {}, "2031-02-29T00:00:00Z", "2031-06-15T11:00:00+00:00",
                      "2031-06-15T11:00:00.1Z", "2031-06-15T24:00:00Z",
                      "2031-06-15T11:00:60Z", "２０３１-06-15T11:00:00Z"):
            with self.subTest(value=value):
                self.docs = copy.deepcopy(original)
                self.mutate_value(lambda v: v.update(valid_from=value))
                self.gap(self.run_case(), "TIME_FORMAT")

    def test_reversed_and_empty_intervals(self):
        for start in ("2031-06-15T13:00:00Z", "2031-06-15T14:00:00Z"):
            self.mutate_value(lambda v: v.update(valid_from=start))
            self.gap(self.run_case(), "INVALID_INTERVAL")

    def test_guard_window_matters_even_when_answer_is_valid(self):
        self.mutate_value(lambda v: v.update(valid_until=self.q["as_of"]), 1)
        self.gap(self.run_case(), "EXPIRED", "authority")

    def test_multiple_failures_are_all_returned_without_partial_values(self):
        for index in (0, 1):
            self.mutate_value(lambda v: v.update(valid_until=self.q["as_of"]), index)
        report = self.run_case()
        self.assertEqual(len(report["time_gaps"]), 2)
        self.assertNotIn("requirements", report)

    def test_source_conflict_precedes_time_check(self):
        self.docs["register"]["observations"][0]["value"]["valid_until"] = self.q["as_of"]
        report = self.run_case()
        self.assertEqual(report["gaps"], [dict(id="snapshot", reason="CONFLICT")])
        self.assertNotIn("time_gaps", report)
        self.assertNotIn("requirements", report)

    def test_question_errors_refuse_before_source_reads(self):
        original = copy.deepcopy(self.q)
        mutations = [
            lambda q:q.update(as_of="now"), lambda q:q.update(as_of=None),
            lambda q:q.update(as_of="2031-02-30T00:00:00Z"),
            lambda q:q.update(schema_version=True), lambda q:q.update(schema_version=3),
            lambda q:q.update(time_constraints=[]),
            lambda q:q["time_constraints"][0].update(requirement="undeclared"),
            lambda q:q["time_constraints"][0].update(valid_from="/bad~9"),
            lambda q:q["time_constraints"][0].update(valid_until="/valid_from"),
            lambda q:q["time_constraints"].append(copy.deepcopy(q["time_constraints"][0])),
            lambda q:q["time_constraints"][0].update(extra=True),
            lambda q:q.pop("as_of")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.q = copy.deepcopy(original); mutate(self.q)
                report = self.run_case()
                self.assertEqual(report["status"], "REFUSED", report)
                self.assertEqual(report["metrics"]["source_reads"], 0)
                self.assertNotIn("requirements", report)

    def test_only_declared_time_constraints_are_checked(self):
        self.q["time_constraints"].pop()
        self.mutate_value(lambda v: v.update(valid_until="2000-01-01T00:00:00Z"), 1)
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertEqual(len(report["time_checks"]), 1)

    def test_nested_and_escaped_pointers(self):
        for row in self.q["time_constraints"]:
            row.update(valid_from="/window~1utc/0", valid_until="/window~1utc/1")
        for index in (0, 1):
            self.mutate_value(lambda v: v.update({"window/utc": [v.pop("valid_from"), v.pop("valid_until")]}), index)
        self.assertEqual(self.run_case()["status"], "OBSERVED")

    def test_no_additional_source_reads(self):
        with patch.object(E, "read_regular", wraps=E.read_regular) as read:
            report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertEqual(read.call_count, 3)
        self.assertEqual(report["metrics"]["source_reads"], 2)

    def test_result_limit_counts_time_metadata(self):
        length = len(E.encode(self.run_case()))
        self.q["max_result_bytes"] = length
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertEqual(len(E.encode(report)), length)
        self.q["max_result_bytes"] -= 1
        report = self.run_case()
        self.assertEqual(report["status"], "REFUSED")
        self.assertNotIn("requirements", report)

    def test_unconstrained_v1_has_no_time_metadata(self):
        self.q["schema_version"] = 1
        del self.q["as_of"]; del self.q["time_constraints"]
        self.mutate_value(lambda v: v.update(valid_until=None))
        report = self.run_case()
        self.assertEqual(report["status"], "OBSERVED")
        self.assertNotIn("time_checks", report)
        self.assertNotIn("as_of", report)

    def test_documented_commands_match_pins_and_exit_codes(self):
        repo = Path(__file__).resolve().parents[1]
        doc = (repo / "docs/temporal-requirements.md").read_text(encoding="utf-8")
        commands = [line for line in doc.splitlines() if line.startswith("python tools/read_requirement_sources.py ")]
        self.assertEqual(len(commands), 2)
        for line, code in zip(commands, (0, 1)):
            command = shlex.split(line)
            p = subprocess.run([sys.executable, "-E", *command[1:]], cwd=repo,
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, code, p.stdout + p.stderr)
            report = E.load_json(p.stdout.encode("utf-8"))
            self.assertEqual(report["status"], "OBSERVED" if code == 0 else "INSUFFICIENT")


if __name__ == "__main__":
    unittest.main()

