"""Validate oracle scoring and the real benchmark CLI, including negative controls."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

import benchmark_swarm as B


class BenchmarkTests(unittest.TestCase):
    def test_shipped_oracle_runs_both_standalone_planners(self):
        original = B.DEFAULT_CASES.read_bytes()
        for package in ('project', 'research'):
            with self.subTest(package=package):
                path = B.ROOT / f'.agents/skills/run-diverse-luna-{package}/scripts/plan_swarm.py'
                result = subprocess.run([sys.executable, str(Path(B.__file__)), '--planner', str(path)],
                                        capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['passed'], report['total'])
                self.assertGreaterEqual(report['total'], 15)
                self.assertLess(report['ablation_selection_correct']['wave_barrier'], report['total'])
                self.assertLess(report['ablation_selection_correct']['all_planned'], report['total'])
                self.assertFalse(report['communication']['dependency_only']['exact_expected_deliveries'])
                self.assertTrue(report['communication']['dependency_epoch_dedup']['exact_expected_deliveries'])
        self.assertEqual(B.DEFAULT_CASES.read_bytes(), original)

    def test_wrong_oracle_fails_and_cannot_be_learned_from_output(self):
        spec = importlib.util.spec_from_file_location('benchmark_test_planner', B.DEFAULT_PLANNER)
        planner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(planner)
        document = json.loads(B.DEFAULT_CASES.read_text(encoding='utf-8'))
        document['cases'][0]['expected']['selected_attempt_ids'] = ['V']
        report = B.run_benchmark(document, planner)
        self.assertFalse(report['cases'][0]['passed'])
        self.assertEqual(report['cases'][0]['unexpected_starts'], ['A', 'D'])
        self.assertEqual(report['cases'][0]['missed_ready'], ['V'])
        self.assertEqual(report['passed'], report['total'] - 1)

    def test_wrong_blocker_and_error_codes_fail_even_when_no_start(self):
        wanted = dict(selected_attempt_ids=[], blocked_reasons={'B': ['DEPENDENCY_FAILED']}, errors=[])
        actual = dict(selected_attempt_ids=[], blocked=[dict(attempt_id='B', reasons=[dict(code='CAPACITY_OR_WAVE_LIMIT')])])
        self.assertFalse(B.score(wanted, actual)['passed'])
        self.assertFalse(B.score(dict(selected_attempt_ids=[], errors=['INVALID_LEDGER']), {})['passed'])

    def test_extra_blocked_attempt_or_reason_cannot_pass(self):
        wanted = dict(selected_attempt_ids=['A'], blocked_reasons={'B': ['DEPENDENCY_NOT_ACCEPTED']})
        actual = dict(selected_attempt_ids=['A'], blocked=[
            dict(attempt_id='B', reasons=[dict(code='DEPENDENCY_NOT_ACCEPTED'), dict(code='WRONG_REASON')]),
            dict(attempt_id='INVENTED', reasons=[dict(code='DEPENDENCY_FAILED')])])
        result = B.score(wanted, actual)
        self.assertFalse(result['passed'])
        self.assertEqual(result['unexpected_blocked'], ['INVENTED'])
        self.assertEqual(result['unexpected_blocker_reasons']['B'], ['WRONG_REASON'])

    def test_fixture_hygiene_rejects_empty_duplicate_and_unknown_cases(self):
        document = json.loads(B.DEFAULT_CASES.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            B.run_benchmark(dict(document, cases=[]), None)
        with self.assertRaises(ValueError):
            B.run_benchmark(dict(document, cases=[document['cases'][0]] * 2), None)
        bad = copy.deepcopy(document['cases'][0])
        bad['row_overrides'] = {'missing': {'wave': 7}}
        with self.assertRaises(ValueError):
            B.materialize(document, bad)

    def test_duplicate_blocked_reports_fail_without_losing_reasons(self):
        wanted = dict(selected_attempt_ids=['A'], blocked_reasons={'B': ['DEPENDENCY_NOT_ACCEPTED']})
        correct = dict(attempt_id='B', reasons=[dict(code='DEPENDENCY_NOT_ACCEPTED')])
        wrong = dict(attempt_id='B', reasons=[dict(code='WRONG_REASON')])
        # A contradictory report must fail in either arrival order. Identical
        # duplicates are invalid too, even though set equality would hide them.
        for rows in ([wrong, correct], [correct, wrong], [correct, correct]):
            with self.subTest(rows=rows):
                actual = dict(selected_attempt_ids=['A'], blocked=copy.deepcopy(rows))
                before = copy.deepcopy(actual)
                result = B.score(wanted, actual)
                self.assertFalse(result['passed'])
                self.assertFalse(result['blocker_reasons_correct'])
                self.assertEqual(result['duplicate_blocked'], ['B'])
                self.assertEqual(result['unexpected_blocker_reasons'],
                                 {'B': ['WRONG_REASON']} if wrong in rows else {})
                self.assertEqual(actual, before)

    def test_single_report_reason_order_and_distinct_attempts_remain_valid(self):
        wanted = dict(selected_attempt_ids=[], blocked_reasons={'B': ['ONE', 'TWO'], 'C': ['ONE']})
        actual = dict(selected_attempt_ids=[], blocked=[
            dict(attempt_id='C', reasons=[dict(code='ONE')]),
            dict(attempt_id='B', reasons=[dict(code='TWO'), dict(code='ONE')])])
        result = B.score(wanted, actual)
        self.assertTrue(result['passed'])
        self.assertEqual(result['duplicate_blocked'], [])


if __name__ == '__main__':
    unittest.main()
