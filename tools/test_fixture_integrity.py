import copy
import json
import subprocess
import sys
import unittest

from example_fixture_builder import ORACLE, SPECS, build_cases, builder
from fixture_integrity import check_builder


class FixtureIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.ids = list(SPECS)
        self.oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
        self.expected = self.oracle["expected_cases"]

    def check(self, build):
        return check_builder(build, self.ids, self.expected)

    def test_preregistered_generator_controls(self):
        for case in self.oracle["variants"]:
            with self.subTest(variant=case["id"]):
                report = self.check(builder(case["id"]))
                self.assertIs(report["passes"], case["accept"])
                self.assertIs(report["order_independent"], case["order_independent"])

    def test_independent_cases_match_reviewed_oracle_without_mutating_it(self):
        before = copy.deepcopy(self.expected)
        result = self.check(build_cases)
        self.assertTrue(result["passes"])
        self.assertEqual(result["builder_calls"], 4)
        self.assertEqual(len(set(result["snapshot_sha256"].values())), 1)
        self.assertEqual(self.expected, before)

    def test_aliasing_changes_earlier_input_and_fails(self):
        result = self.check(lambda order: build_cases(order, shared=True))
        self.assertFalse(result["passes"])
        self.assertFalse(result["order_independent"])
        self.assertTrue(result["oracle_mismatches"])

    def test_stable_wrong_answer_requires_oracle_not_just_order(self):
        def build(order):
            rows = build_cases(order)
            for row in rows:
                row["expected"]["ready"] = True
            return rows
        result = self.check(build)
        self.assertTrue(result["order_independent"])
        self.assertFalse(result["matches_reviewed_cases"])
        self.assertFalse(result["passes"])

    def test_type_changes_and_list_order_remain_significant(self):
        for value in (True, 41.0, "41", None):
            def build(order):
                rows = build_cases(order)
                next(r for r in rows if r["id"] == "alpha")["expected"]["revision"] = value
                return rows
            self.assertFalse(self.check(build)["passes"])
        def build(order):
            rows = build_cases(order)
            for row in rows:
                row["input"]["tags"].reverse()
            return rows
        self.assertFalse(self.check(build)["passes"])

    def test_dictionary_and_outer_case_order_are_not_semantic(self):
        def build(order):
            return [dict(reversed(list(row.items()))) for row in build_cases(order)[::-1]]
        self.assertTrue(self.check(build)["passes"])

    def test_missing_duplicate_and_extra_cases_never_partially_pass(self):
        for mutation in (lambda rows: rows[:-1], lambda rows: rows + [rows[0]],
                         lambda rows: rows + [dict(rows[0], id="extra")]):
            result = self.check(lambda order: mutation(build_cases(order)))
            self.assertFalse(result["passes"])
            self.assertIsNone(result["order_independent"])
            self.assertEqual(len(result["build_errors"]), 4)

    def test_repeat_build_detects_retained_state(self):
        calls = []
        def build(order):
            calls.append(order)
            rows = build_cases(order)
            if len(calls) == 4:
                rows[0]["expected"]["status"] = "stale"
            return rows
        result = self.check(build)
        self.assertFalse(result["passes"])
        self.assertEqual(result["order_changes"][0]["order"], "repeat-forward")

    def test_invalid_oracle_and_ids_fail_before_builder_runs(self):
        def never(order):
            self.fail("builder must not run")
        for ids, expected in [
                (["alpha"], self.expected), (["alpha", "alpha"], self.expected),
                (["alpha", True], self.expected), (self.ids, self.expected[:-1]),
                (self.ids, self.expected + [self.expected[0]])]:
            with self.assertRaises(ValueError):
                check_builder(never, ids, expected)

    def test_invalid_json_and_builder_failure_are_not_accepted(self):
        cyclic = []; cyclic.append(cyclic)
        for value in (float("nan"), float("inf"), {1: "wrong key"}, (1, 2), cyclic):
            def build(order):
                rows = build_cases(order)
                rows[0]["input"] = value
                return rows
            result = self.check(build)
            self.assertFalse(result["passes"])
            self.assertEqual(len(result["build_errors"]), 4)
        def failed(order):
            raise RuntimeError("synthetic failure")
        self.assertFalse(self.check(failed)["passes"])

    def test_executable_good_and_bad_examples(self):
        from pathlib import Path
        script = Path(__file__).with_name("example_fixture_builder.py")
        for args, code in (([], 0), (["--variant", "shared-input"], 1)):
            result = subprocess.run([sys.executable, str(script), *args], capture_output=True,
                                    text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual(json.loads(result.stdout)["passes"], code == 0)


if __name__ == "__main__":
    unittest.main()
