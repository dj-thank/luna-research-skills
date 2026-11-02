"""Truth labels, evidence identity and complete work accounting are distinct gates."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_comparison as C

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.data = (FIXTURES / 'comparison_evidence.json').read_bytes()
        self.pin = hashlib.sha256(self.data).hexdigest()
        self.doc = C.load_json(self.data)
        self.report = C.load_json((FIXTURES / 'comparison_report.json').read_bytes())

    def check_changed(self, doc):
        data = json.dumps(doc).encode('utf-8')
        return C.check(data, hashlib.sha256(data).hexdigest())

    def test_frozen_example_and_calibration_accounting(self):
        result = C.check(self.data, self.pin, self.report)
        self.assertTrue(result['consistent'], result['errors'])
        self.assertEqual(result['summary']['metrics']['candidate']['total_calls'], 10)
        self.assertTrue(result['summary']['passes_case_gate'])

    def test_aggregate_gain_with_case_loss_is_rejected_for_promotion(self):
        self.doc['cases'][0]['choices']['candidate'] = None
        result = self.check_changed(self.doc)['summary']
        self.assertGreater(result['metrics']['candidate']['correct'], result['metrics']['baseline']['correct'])
        self.assertEqual(result['regressions'], ['stable'])
        self.assertFalse(result['passes_case_gate'])
        data = json.dumps(self.doc).encode()
        self.assertTrue(C.check(data, hashlib.sha256(data).hexdigest(), result)['consistent'])

    def test_no_gain_and_false_accept_do_not_pass_case_gate(self):
        for case in self.doc['cases']:
            case['choices']['candidate'] = case['choices']['baseline']
        self.assertFalse(self.check_changed(self.doc)['summary']['passes_case_gate'])
        self.doc = C.load_json(self.data)
        self.doc['cases'][-1]['choices']['candidate'] = 'wrong'
        result = self.check_changed(self.doc)['summary']
        self.assertEqual(result['metrics']['candidate']['false_accept'], 1)
        self.assertFalse(result['passes_case_gate'])

    def test_omitted_calibration_and_self_certified_correctness(self):
        for mutate in ('calibration', 'false_accept', 'regressions', 'unit', 'pin'):
            report = copy.deepcopy(self.report)
            if mutate == 'calibration':
                report['metrics']['candidate'].update(calibration_calls=0, total_calls=8)
            elif mutate == 'false_accept':
                report['metrics']['baseline'].update(correct=2, false_accept=0)
            elif mutate == 'regressions':
                report['regressions'] = ['stable']
            elif mutate == 'unit':
                report['work_unit'] = 'simulated_judge_lookup'
            else:
                report['evidence_sha256'] = '0' * 64
            with self.subTest(mutate=mutate):
                self.assertFalse(C.check(self.data, self.pin, report)['consistent'])

    def test_stale_pin_cannot_be_replaced_by_report_digest(self):
        for field in ('work', 'cases'):
            doc = copy.deepcopy(self.doc)
            doc[field].pop()
            data = json.dumps(doc).encode()
            report = copy.deepcopy(self.report)
            report['evidence_sha256'] = hashlib.sha256(data).hexdigest()
            self.assertFalse(C.check(data, self.pin, report)['consistent'])

    def test_byte_identity_includes_whitespace(self):
        self.assertFalse(C.check(self.data + b' ', self.pin, self.report)['consistent'])

    def test_malformed_pin(self):
        for pin in (None, 'X' * 64, '0' * 63, True):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                C.check(self.data, pin)

    def test_duplicate_case_work_and_answer_ids(self):
        for field in ('cases', 'work', 'valid_answers', 'available_answers'):
            doc = copy.deepcopy(self.doc)
            seq = doc[field] if field in ('cases', 'work') else doc['cases'][0][field]
            seq.append(copy.deepcopy(seq[0]))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check_changed(doc)

    def test_unknown_choice_and_metadata_rejected(self):
        for mutation in ('choice', 'extra', 'role', 'phase', 'calibration_case', 'missing_case'):
            doc = copy.deepcopy(self.doc)
            if mutation == 'choice': doc['cases'][0]['choices']['candidate'] = 'invented'
            if mutation == 'extra': doc['passed'] = True
            if mutation == 'role': doc['work'][0]['policy'] = 'unknown'
            if mutation == 'phase': doc['work'][0]['phase'] = 'unknown'
            if mutation == 'calibration_case': doc['work'][-1]['case_id'] = 'stable'
            if mutation == 'missing_case': doc['work'][0]['case_id'] = 'unknown'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check_changed(doc)

    def test_budget_and_schema_reject_booleans_and_fractional_values(self):
        for key in ('schema_version', 'per_case_budget'):
            for value in (True, 1.0, 0, '1'):
                doc = copy.deepcopy(self.doc); doc[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.check_changed(doc)
        doc = copy.deepcopy(self.doc)
        extra = dict(doc['work'][0], id='over-budget')
        doc['work'].extend([extra, dict(extra, id='over-budget-2')])
        with self.assertRaises(ValueError): self.check_changed(doc)

    def test_report_requires_exact_fields_and_numeric_types(self):
        for key, value in (('total_cases', 5.0), ('passes_case_gate', 1), ('extra', True)):
            report = copy.deepcopy(self.report); report[key] = value
            self.assertFalse(C.check(self.data, self.pin, report)['consistent'])
        self.report['metrics']['baseline']['correct'] = True
        self.assertFalse(C.check(self.data, self.pin, self.report)['consistent'])
        self.assertFalse(C.check(self.data, self.pin, [])['consistent'])

    def test_json_duplicate_keys_and_nonfinite_constants(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError): C.load_json(text)

    def test_simulated_work_remains_separate_and_inputs_unmodified(self):
        original = copy.deepcopy(self.doc)
        self.check_changed(self.doc)
        self.assertEqual(original, self.doc)
        self.doc['work_unit'] = 'simulated_judge_lookup'
        self.assertEqual(self.check_changed(self.doc)['summary']['work_unit'], 'simulated_judge_lookup')

    def test_cli_exit_codes_and_read_only_behavior(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence, report = root/'evidence.json', root/'report.json'
            evidence.write_bytes(self.data)
            report.write_text(json.dumps(self.report), encoding='utf-8')
            command = [sys.executable, C.__file__, '--evidence', str(evidence), '--sha256', self.pin]
            def run(extra):
                result = subprocess.run(command + extra, capture_output=True, text=True, encoding='utf-8', timeout=30)
                return result.returncode, json.loads(result.stdout)
            snapshot = {p.name:p.read_bytes() for p in root.iterdir()}
            code, summary = run([])
            self.assertEqual(code, 0); self.assertEqual(summary, self.report)
            self.assertEqual(run(['--report', str(report)])[0], 0)
            self.assertEqual(snapshot, {p.name:p.read_bytes() for p in root.iterdir()})
            self.report['passes_case_gate'] = False
            report.write_text(json.dumps(self.report), encoding='utf-8')
            self.assertEqual(run(['--report', str(report)])[0], 1)
            report.write_text('null', encoding='utf-8')
            self.assertEqual(run(['--report', str(report)])[0], 2)
            report.write_text('{"x":1,"x":2}', encoding='utf-8')
            self.assertEqual(run(['--report', str(report)])[0], 2)
            evidence.write_text('{}', encoding='utf-8')
            self.assertEqual(run([])[0], 1)
            command[-1] = hashlib.sha256(b'{}').hexdigest()
            self.assertEqual(run([])[0], 2)


if __name__ == '__main__':
    unittest.main()
