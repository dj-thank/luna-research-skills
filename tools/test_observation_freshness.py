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


class ObservationFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        fixture = Path(__file__).with_name("fixtures")
        self.q = E.load_json((fixture / "freshness_question.json").read_bytes())
        self.docs = {s: E.load_json((fixture / ("freshness_" + s + ".json")).read_bytes())
                     for s in ("sender", "register")}

    def run_case(self):
        for sid, doc in self.docs.items():
            raw = E.encode(doc); (self.root / (sid + ".json")).write_bytes(raw)
            next(s for s in self.q["sources"] if s["id"] == sid)["sha256"] = E.digest(raw)
        raw = E.encode(self.q); path = self.root / "q.json"; path.write_bytes(raw)
        return C.read_sources(path, E.digest(raw), [(s, self.root / (s + ".json")) for s in self.docs])

    def change(self, callback, index=0):
        for doc in self.docs.values():
            callback(doc["observations"][index]["value"])

    def gap(self, report, reason, requirement="snapshot"):
        self.assertEqual(report["status"], "INSUFFICIENT", report)
        self.assertEqual(report["freshness_gaps"], [
            dict(id=requirement + "-age", requirement=requirement, reason=reason)])
        self.assertNotIn("requirements", report)
        self.assertNotIn("freshness_checks", report)

    def test_complete_preserves_records_and_reports_exact_age_and_limit(self):
        r = self.run_case()
        self.assertEqual(r["status"], "OBSERVED")
        self.assertEqual(r["freshness_checks"], [
            dict(id=n + "-age", requirement=n, status="WITHIN_MAX_AGE", age_seconds=300, max_age_seconds=600)
            for n in ("snapshot", "authority")])
        self.assertEqual(r["scope"], "declared_requirements_sources_time_and_freshness_only")
        for req in r["requirements"]:
            for o in req["observations"]:
                original = next(x for x in self.docs[o["origin"]["id"]]["observations"] if x["id"] == o["id"])
                self.assertEqual({k:v for k,v in o.items() if k != "origin"}, original)

    def test_maximum_age_is_inclusive_and_one_second_older_is_stale(self):
        self.change(lambda v:v.update(observed_at="2033-03-01T11:50:00Z"))
        self.assertEqual(self.run_case()["status"], "OBSERVED")
        self.change(lambda v:v.update(observed_at="2033-03-01T11:49:59Z"))
        self.gap(self.run_case(), "STALE")

    def test_zero_age_requires_the_same_second(self):
        self.q["freshness_constraints"][0]["max_age_seconds"] = 0
        self.change(lambda v:v.update(observed_at=self.q["as_of"]))
        self.assertEqual(self.run_case()["status"], "OBSERVED")
        self.change(lambda v:v.update(observed_at="2033-03-01T11:59:59Z"))
        self.gap(self.run_case(), "STALE")

    def test_future_observation_is_not_clamped_or_absolute_valued(self):
        self.change(lambda v:v.update(observed_at="2033-03-01T12:00:01Z"))
        self.gap(self.run_case(), "FUTURE_OBSERVATION")

    def test_historical_query_uses_its_clock_and_preserves_negative_facts(self):
        self.q["as_of"] = "1995-07-01T12:00:00Z"
        for index in (0, 1):
            self.change(lambda v:v.update(valid_from="1995-07-01T00:00:00Z",valid_until="1995-07-02T00:00:00Z",
                                         observed_at="1995-07-01T11:55:00Z",fact=False), index)
        r = self.run_case()
        self.assertEqual(r["status"], "OBSERVED")
        self.assertTrue(all(c["age_seconds"] == 300 for c in r["freshness_checks"]))
        self.assertIs(r["requirements"][1]["observations"][0]["value"]["fact"], False)

    def test_recent_receipt_cannot_refresh_old_observation(self):
        self.change(lambda v:v.update(observed_at="2033-02-28T12:00:00Z",received_at=self.q["as_of"]))
        self.gap(self.run_case(), "STALE")

    def test_null_observation_is_unknown(self):
        self.change(lambda v:v.update(observed_at=None))
        self.gap(self.run_case(), "UNKNOWN")

    def test_missing_observation_is_not_another_timestamp(self):
        self.change(lambda v:v.pop("observed_at"))
        self.gap(self.run_case(), "MISSING")

    def test_bad_observation_type_calendar_offset_precision_and_leap_second(self):
        original = copy.deepcopy(self.docs)
        for value in (False, 300, [], {}, "2033-02-29T11:55:00Z", "2033-03-01T11:55:00+00:00",
                      "2033-03-01T11:55:00.1Z", "2033-03-01T11:55:60Z"):
            with self.subTest(value=value):
                self.docs = copy.deepcopy(original)
                self.change(lambda v:v.update(observed_at=value))
                self.gap(self.run_case(), "TIME_FORMAT")

    def test_stale_guard_is_not_covered_by_fresh_answer(self):
        self.change(lambda v:v.update(observed_at="2033-03-01T11:49:59Z"), 1)
        self.gap(self.run_case(), "STALE", "authority")

    def test_all_freshness_gaps_without_partial_success_checks(self):
        for index in (0, 1):
            self.change(lambda v:v.update(observed_at=None), index)
        r = self.run_case()
        self.assertEqual(len(r["freshness_gaps"]), 2)
        self.assertNotIn("requirements", r)
        self.assertNotIn("freshness_checks", r)

    def test_validity_failure_precedes_freshness(self):
        self.change(lambda v:v.update(valid_until=self.q["as_of"],observed_at=None))
        r = self.run_case()
        self.assertEqual(r["time_gaps"][0]["reason"], "EXPIRED")
        self.assertNotIn("freshness_gaps", r)

    def test_source_conflict_never_chooses_the_newest_observation(self):
        self.docs["register"]["observations"][0]["value"]["observed_at"] = self.q["as_of"]
        r = self.run_case()
        self.assertEqual(r["gaps"], [dict(id="snapshot",reason="CONFLICT")])
        self.assertNotIn("freshness_gaps", r)
        self.assertNotIn("requirements", r)

    def test_bad_question_refuses_before_sources(self):
        original = copy.deepcopy(self.q)
        mutations = [lambda q:q.pop("freshness_constraints"),
                     lambda q:q.update(freshness_constraints=[]),
                     lambda q:q.update(freshness_constraints={}),
                     lambda q:q["freshness_constraints"][0].update(requirement="undeclared"),
                     lambda q:q["freshness_constraints"][0].update(observed_at="/bad~2"),
                     lambda q:q["freshness_constraints"][0].update(extra=True),
                     lambda q:q["freshness_constraints"].append(copy.deepcopy(q["freshness_constraints"][0]))]
        mutations += [lambda q,v=v:q["freshness_constraints"][0].update(max_age_seconds=v)
                      for v in (-1, True, 600.0, "600", None, C.MAX_AGE_SECONDS + 1)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.q = copy.deepcopy(original); mutate(self.q)
                r = self.run_case()
                self.assertEqual(r["status"], "REFUSED", r)
                self.assertEqual(r["metrics"]["source_reads"], 0)

    def test_only_declared_observation_age_constraints_are_checked(self):
        self.q["freshness_constraints"].pop()
        self.change(lambda v:v.update(observed_at=None), 1)
        r = self.run_case()
        self.assertEqual(r["status"], "OBSERVED")
        self.assertEqual(len(r["freshness_checks"]), 1)

    def test_nested_and_escaped_pointer(self):
        for row in self.q["freshness_constraints"]:
            row["observed_at"] = "/observation~1utc/0"
        for index in (0, 1):
            self.change(lambda v:v.update({"observation/utc":[v.pop("observed_at")]}), index)
        self.assertEqual(self.run_case()["status"], "OBSERVED")

    def test_no_additional_source_reads(self):
        with patch.object(E, "read_regular", wraps=E.read_regular) as read:
            r = self.run_case()
        self.assertEqual(r["status"], "OBSERVED")
        self.assertEqual(read.call_count, 3)
        self.assertEqual(r["metrics"]["source_reads"], 2)

    def test_result_limit_includes_age_and_threshold_metadata(self):
        length = len(E.encode(self.run_case()))
        self.q["max_result_bytes"] = length
        self.assertEqual(len(E.encode(self.run_case())), length)
        self.assertEqual(self.run_case()["status"], "OBSERVED")
        self.q["max_result_bytes"] -= 1
        r = self.run_case()
        self.assertEqual(r["status"], "REFUSED")
        self.assertNotIn("requirements", r)

    def test_supported_calendar_span_does_not_overflow(self):
        self.q["as_of"] = "9999-12-31T23:59:58Z"
        for row in self.q["freshness_constraints"]:
            row["max_age_seconds"] = C.MAX_AGE_SECONDS
        for index in (0, 1):
            self.change(lambda v:v.update(valid_from="0001-01-01T00:00:00Z",valid_until="9999-12-31T23:59:59Z",
                                         observed_at="0001-01-01T00:00:00Z"), index)
        r = self.run_case()
        self.assertEqual(r["status"], "OBSERVED")
        self.assertTrue(all(c["age_seconds"] == 315537897598 for c in r["freshness_checks"]))

    def test_documented_commands_and_pins(self):
        repo = Path(__file__).resolve().parents[1]
        doc = (repo / "docs/observation-freshness.md").read_text(encoding="utf-8")
        commands = [line for line in doc.splitlines() if line.startswith("python tools/read_requirement_sources.py ")]
        self.assertEqual(len(commands), 2)
        for line, code in zip(commands, (0, 1)):
            command = shlex.split(line)
            p = subprocess.run([sys.executable, "-E", *command[1:]],cwd=repo,capture_output=True,text=True,encoding="utf-8")
            self.assertEqual(p.returncode, code, p.stdout + p.stderr)
            self.assertEqual(E.load_json(p.stdout.encode("utf-8"))["status"], "OBSERVED" if code == 0 else "INSUFFICIENT")


if __name__ == "__main__":
    unittest.main()

