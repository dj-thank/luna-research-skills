"""Adversarial controls for bounded deterministic verification reuse."""
import copy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import benchmark_review as R


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(R.DEFAULT_CASES.read_text(encoding='utf-8'))
        self.expected = self.doc['oracle']
        self.good = self.doc['proposals']['good']

    def test_cli_frozen_comparison_preserves_negative_candidate(self):
        original = R.DEFAULT_CASES.read_bytes()
        run = subprocess.run([sys.executable, R.__file__], capture_output=True, text=True,
                             encoding='utf-8', timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report['passed'], 12)
        self.assertEqual(report['total'], 12)
        self.assertFalse(report['comparisons']['checked_minority']['passes_case_gate'])
        self.assertTrue(report['comparisons']['unique_critique']['passes_case_gate'])
        self.assertEqual(report['metrics']['unique_critique']['oracle_calls'], 22)
        self.assertEqual(R.DEFAULT_CASES.read_bytes(), original)

    def test_every_context_component_invalidates_reuse(self):
        changes = [dict(expected=dict(selected_attempt_ids=['B'])),
                   dict(proposal=self.doc['proposals']['wrong']),
                   dict(revision='changed'), dict(epoch=2)]
        for change in changes:
            with self.subTest(change=change):
                budget = R.OracleBudget(2)
                args = dict(expected=self.expected, proposal=self.good, revision='r1', epoch=1, reuse=True)
                self.assertTrue(budget.check(**args))
                budget.check(**dict(args, **change))
                self.assertEqual(budget.calls, 2)
                self.assertEqual(budget.hits, 0)

    def test_false_verdict_reused_by_content_not_proposal_name(self):
        budget = R.OracleBudget(2)
        args = dict(expected=self.expected, revision='r1', epoch=1, reuse=True)
        self.assertFalse(budget.check(proposal=self.doc['proposals']['wrong'], **args))
        self.assertFalse(budget.check(proposal=self.doc['proposals']['wrong_alias'], **args))
        self.assertEqual((budget.calls, budget.hits), (1, 1))
        self.assertTrue(budget.check(proposal=self.good, **args))
        self.assertEqual(budget.calls, 2)

    def test_exhaustion_is_unchecked_and_cached_success_does_not_spend(self):
        budget = R.OracleBudget(1)
        args = dict(expected=self.expected, revision='r1', epoch=1, reuse=True)
        self.assertTrue(budget.check(proposal=self.good, **args))
        self.assertIsNone(budget.check(proposal=self.doc['proposals']['wrong'], **args))
        self.assertTrue(budget.check(proposal=copy.deepcopy(self.good), **args))
        self.assertEqual((budget.calls, budget.hits), (1, 1))

    def test_exception_consumes_budget_and_is_not_cached(self):
        budget = R.OracleBudget(1)
        args = dict(expected=self.expected, proposal=self.good, revision='r1', epoch=1, reuse=True)
        with patch.object(R.B, 'score', side_effect=ValueError('injected')) as score:
            with self.assertRaises(ValueError):
                budget.check(**args)
            self.assertIsNone(budget.check(**args))
            self.assertEqual(score.call_count, 1)
        self.assertEqual((budget.calls, budget.hits), (1, 0))

    def test_wrong_expectation_or_label_fails_without_rewriting_oracle(self):
        for key in ('expected', 'label', 'calls'):
            with self.subTest(key=key):
                doc = copy.deepcopy(self.doc)
                if key == 'expected':
                    doc['cases'][0]['expected']['unique_critique'] = None
                elif key == 'label':
                    doc['valid_labels']['good'] = False
                else:
                    doc['cases'][0]['expected_calls']['unique_critique'] = 1
                frozen = copy.deepcopy(doc)
                report = R.run_benchmark(doc)
                self.assertLess(report['passed'], report['total'])
                self.assertFalse(report['comparisons']['unique_critique']['passes_case_gate'])
                self.assertEqual(doc, frozen)

    def test_invalid_fixtures_and_ties_rejected(self):
        mutations = [dict(cases=[]), dict(cases=[self.doc['cases'][0]]*2), dict(budget=True),
                     dict(valid_labels=dict(self.doc['valid_labels'], good='yes'))]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(ValueError):
                R.run_benchmark(dict(self.doc, **change))
        case = dict(self.doc['cases'][0], independent=['good', 'wrong', 'wrong_other'])
        with self.assertRaises(ValueError):
            R.evaluate(self.doc, case, 'unique_critique', 'r1')
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                R.OracleBudget(limit)


if __name__ == '__main__':
    unittest.main()
