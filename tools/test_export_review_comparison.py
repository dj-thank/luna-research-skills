"""Exercise the producer/consumer boundary with actual scorer attempts."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import export_review_comparison as E


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(E.R.DEFAULT_CASES.read_text(encoding='utf-8'))

    def one(self, name):
        self.doc['cases'] = [c for c in self.doc['cases'] if c['id'] == name]
        self.assertEqual(len(self.doc['cases']), 1)

    def encode(self):
        data = json.dumps(self.doc).encode()
        return data, hashlib.sha256(data).hexdigest()

    def export(self, **kwargs):
        return E.export_evidence(*self.encode(), **kwargs)

    def summarize(self, evidence):
        data = json.dumps(evidence).encode()
        result = E.C.check(data, hashlib.sha256(data).hexdigest())
        self.assertTrue(result['consistent'])
        return result['summary']

    def test_selected_pair_round_trip_counts_actual_work_only(self):
        for policy, correct, calls, gate in [('unique_critique',9,46,True),('checked_minority',8,48,False)]:
            with self.subTest(policy=policy), patch.object(E.R.B, 'score', wraps=E.R.B.score) as spy:
                evidence = self.export(candidate=policy)
                summary = self.summarize(evidence)
                self.assertEqual(spy.call_count, calls)
                self.assertEqual(len(evidence['work']), calls)
                self.assertEqual(summary['metrics']['candidate']['correct'], correct)
                self.assertEqual(summary['passes_case_gate'], gate)
                self.assertEqual(summary['metrics']['candidate']['calibration_calls'], 0)
                self.assertEqual(summary['source']['fixture_sha256'], self.encode()[1])

    def test_cache_hits_success_rejection_and_abstention(self):
        for name, expected in [('duplicate-valid-answer',3),('correct-minority-wrong-critic',4),('unanimous-duplicate-invalid',3)]:
            self.setUp(); self.one(name)
            with self.subTest(name=name), patch.object(E.R.B,'score',wraps=E.R.B.score) as spy:
                evidence = self.export()
                self.assertEqual(spy.call_count, expected)
                self.assertEqual(len(evidence['work']), expected)

    def test_stale_pin_rejected_before_any_call(self):
        raw, pin = self.encode()
        with patch.object(E.R.B,'score') as spy, self.assertRaises(E.ExportRejected) as error:
            E.export_evidence(raw+b' ', pin)
        self.assertFalse(spy.called)
        self.assertEqual(E.failure_report(error.exception)['attempted_calls'], 0)

    def test_failed_calls_preserved_without_partial_evidence(self):
        self.one('both-alternatives-correct')
        original = E.R.B.score
        for failure in (1,3):
            count = 0
            def score(*args):
                nonlocal count
                count += 1
                if count == failure: raise RuntimeError('injected')
                return original(*args)
            with self.subTest(failure=failure), patch.object(E.R.B,'score',side_effect=score), self.assertRaises(E.ExportRejected) as error:
                self.export()
            result = E.failure_report(error.exception)
            self.assertEqual(result['attempted_calls'], failure)
            self.assertEqual(result['failed_calls'], 1)
            self.assertFalse(result['complete'])
            self.assertNotIn('cases', result)
            self.assertNotIn('work', result)

    def test_unexpected_scorer_exception_keeps_audit(self):
        with patch.object(E.R.B,'score',side_effect=ZeroDivisionError('injected')), self.assertRaises(E.ExportRejected) as error:
            self.export()
        self.assertEqual(E.failure_report(error.exception)['failed_calls'], 1)

    def test_frozen_expectations_and_labels_are_not_rewritten(self):
        for mode in ('choice','calls','label'):
            self.setUp(); self.one('both-alternatives-correct')
            case = self.doc['cases'][0]
            if mode == 'choice': case['expected']['checked_critique'] = None
            if mode == 'calls': case['expected_calls']['checked_critique'] = True
            if mode == 'label': self.doc['valid_labels']['good'] = False
            original = copy.deepcopy(self.doc)
            with self.subTest(mode=mode), self.assertRaises(E.ExportRejected) as error:
                self.export()
            self.assertEqual(E.failure_report(error.exception)['attempted_calls'], 2)
            self.assertEqual(self.doc, original)

    def test_new_fixture_identity_is_explicit_and_no_cross_run_cache(self):
        self.one('duplicate-valid-answer')
        first = self.export()
        self.doc['epoch'] = 'new'
        with patch.object(E.R.B,'score',wraps=E.R.B.score) as spy:
            second = self.export()
            self.assertEqual(spy.call_count, 3)
        self.assertNotEqual(first['source']['fixture_sha256'], second['source']['fixture_sha256'])

    def test_source_change_during_execution_refuses_complete_export(self):
        self.one('both-alternatives-correct')
        sources = E._sources(self.encode()[1])
        changed = dict(sources, review_sha256='0'*64)
        with patch.object(E,'_sources',side_effect=[sources,changed]), self.assertRaises(E.ExportRejected) as error:
            self.export()
        self.assertEqual(E.failure_report(error.exception)['attempted_calls'], 4)

    def test_strict_json_and_invalid_fixtures_are_not_evaluated(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{}'):
            with self.subTest(raw=raw), patch.object(E.R.B,'score') as spy, self.assertRaises(E.ExportRejected):
                E.export_evidence(raw, hashlib.sha256(raw).hexdigest())
            self.assertFalse(spy.called)
        with self.assertRaises(E.ExportRejected): self.export(candidate='checked_critique')

    def test_cli_is_readonly_and_failure_is_json(self):
        self.one('duplicate-valid-answer')
        raw, pin = self.encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cases = root/'cases.json'; cases.write_bytes(raw)
            command = [sys.executable,E.__file__,'--cases',str(cases),'--sha256',pin]
            run = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertEqual(self.summarize(json.loads(run.stdout))['metrics']['candidate']['evaluation_calls'],1)
            self.assertEqual(list(root.iterdir()), [cases]); self.assertEqual(cases.read_bytes(), raw)
            command[-1] = '0'*64
            run = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(run.returncode,2)
            self.assertEqual(json.loads(run.stdout)['attempted_calls'],0)

    def test_version_two_source_is_bound_and_version_one_remains_supported(self):
        self.one('duplicate-valid-answer'); evidence=self.export()
        report=self.summarize(evidence)
        self.assertEqual(report['schema_version'],2)
        report['source']['review_sha256']='0'*64
        raw=json.dumps(evidence).encode()
        self.assertFalse(E.C.check(raw,hashlib.sha256(raw).hexdigest(),report)['consistent'])
        for mutation in ('missing','unknown','invalid'):
            changed=copy.deepcopy(evidence)
            if mutation=='missing': del changed['source']
            if mutation=='unknown': changed['source']['unknown']='0'*64
            if mutation=='invalid': changed['source']['review_sha256']='bad'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): self.summarize(changed)
        legacy=dict(evidence,schema_version=1); del legacy['source']
        self.assertEqual(self.summarize(legacy)['schema_version'],1)


if __name__ == '__main__':
    unittest.main()
