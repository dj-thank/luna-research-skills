"""Negative controls and fresh routing challenges for the offline comparison."""
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import benchmark_communication as C


class CommunicationTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(C.DEFAULT_CASES.read_text(encoding='utf-8'))

    def test_real_cli_frozen_answers_and_negative_ablation(self):
        original = C.DEFAULT_CASES.read_bytes()
        run = subprocess.run([sys.executable, C.__file__], capture_output=True, text=True,
                             encoding='utf-8', timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual((report['passed'], report['total']), (14, 14))
        self.assertEqual([report['metrics'][p]['correct_cases'] for p in C.POLICIES], [7, 10, 14])
        self.assertFalse(report['comparisons']['run_scoped']['passes_case_gate'])
        self.assertTrue(report['comparisons']['run_contract_scoped']['passes_case_gate'])
        self.assertEqual(report['metrics']['run_contract_scoped']['unexpected_deliveries'], 0)
        self.assertEqual(report['metrics']['run_contract_scoped']['missing_deliveries'], 0)
        self.assertEqual(C.DEFAULT_CASES.read_bytes(), original)

    def test_wrong_scope_cannot_poison_dedup_in_any_arrival_order(self):
        case = copy.deepcopy(self.doc['cases'][0])
        good = case['events'][0]
        events = [good, dict(good, event_id='wrong-run', run_id='foreign'),
                  dict(good, event_id='wrong-contract', contract_id='old')]
        for permutation in itertools.permutations(events):
            with self.subTest(order=[e['event_id'] for e in permutation]):
                case['events'] = list(permutation)
                before = copy.deepcopy(case)
                self.assertEqual(C.route(case, 'run_contract_scoped'), [['good', 'C']])
                self.assertEqual(case, before)

    def test_same_bytes_for_distinct_consumer_contracts_in_both_orders(self):
        case = next(c for c in self.doc['cases'] if c['id'] == 'different-consumer-contracts')
        for events, wanted in [(case['events'], [['v2', 'C'], ['v1', 'D']]),
                               (case['events'][::-1], [['v1', 'D'], ['v2', 'C']])]:
            self.assertEqual(C.route(dict(case, events=events), 'run_contract_scoped'), wanted)

    def test_distinct_senders_with_same_payload_are_not_duplicates(self):
        case = copy.deepcopy(self.doc['cases'][0])
        case['agents'].append('Q')
        case['current_epochs']['Q'] = 2
        case['recipients']['Q'] = ['C']
        case['consumer_contracts']['C']['Q'] = 'api-v2'
        case['events'].append(dict(case['events'][0], event_id='q-good', sender='Q'))
        case['expected_deliveries'].append(['q-good', 'C'])
        C.validate(dict(schema_version=1, cases=[case]))
        self.assertEqual(C.route(case, 'run_contract_scoped'), [['good', 'C'], ['q-good', 'C']])

    def test_snapshot_change_does_not_reuse_prior_dedup_or_contract_state(self):
        case = copy.deepcopy(self.doc['cases'][0])
        self.assertEqual(C.route(case, 'run_contract_scoped'), [['good', 'C']])
        case['run_id'] = 'next-run'
        self.assertEqual(C.route(case, 'run_contract_scoped'), [])
        case['events'][0]['run_id'] = 'next-run'
        self.assertEqual(C.route(case, 'run_contract_scoped'), [['good', 'C']])
        case['consumer_contracts']['C']['P'] = 'next-contract'
        self.assertEqual(C.route(case, 'run_contract_scoped'), [])
        case['events'][0]['contract_id'] = 'next-contract'
        self.assertEqual(C.route(case, 'run_contract_scoped'), [['good', 'C']])

    def test_scorer_preserves_duplicate_and_order_failures(self):
        wanted = [['a', 'C'], ['b', 'D']]
        repeated = C.delivery_score(wanted, wanted + [['a', 'C']])
        self.assertFalse(repeated['correct'])
        self.assertEqual(repeated['unexpected_deliveries'], [['a', 'C']])
        self.assertFalse(C.delivery_score(wanted, wanted[::-1])['correct'])

    def test_bad_fixtures_fail_before_policy_execution(self):
        mutations = [lambda d: d.update(schema_version=True), lambda d: d.update(cases=[]),
                     lambda d: d['cases'].append(copy.deepcopy(d['cases'][0])),
                     lambda d: d['cases'][0]['events'].append(copy.deepcopy(d['cases'][0]['events'][0])),
                     lambda d: d['cases'][0]['events'][0].update(epoch=True),
                     lambda d: d['cases'][0]['events'][0].update(sender='unknown'),
                     lambda d: d['cases'][0]['recipients']['P'].append('C'),
                     lambda d: d['cases'][0].update(consumer_contracts={}),
                     lambda d: d['cases'][0]['expected_deliveries'].append(['missing', 'C'])]
        for mutate in mutations:
            bad = copy.deepcopy(self.doc); mutate(bad)
            with self.assertRaises(ValueError):
                C.run_benchmark(bad)

    def test_wrong_answer_and_invalid_input_have_distinct_cli_status(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'cases.json'
            for document, status in [(dict(self.doc, schema_version=99), 2), (self.doc, 1)]:
                document = copy.deepcopy(document)
                if status == 1:
                    document['cases'][0]['expected_deliveries'] = []
                path.write_text(json.dumps(document), encoding='utf-8')
                run = subprocess.run([sys.executable, C.__file__, '--cases', str(path)],
                                     capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(run.returncode, status, run.stdout + run.stderr)
                self.assertEqual(run.stderr, '')
                self.assertIsInstance(json.loads(run.stdout), dict)


if __name__ == '__main__':
    unittest.main()
