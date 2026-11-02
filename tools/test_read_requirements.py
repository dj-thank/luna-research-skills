import copy
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

import read_evidence as E
import read_requirements as R


class ReadRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source.json'
        self.question = self.root/'question.json'
        self.document = dict(schema_version=1, observations=[
            dict(id='change', subject='r2', requirement='change', state='known', value='修正', qualifiers=['Local only']),
            dict(id='tests', subject='r2', requirement='tests', state='known', value=False, qualifiers=['Tests failed']),
            dict(id='other-tests', subject='r1', requirement='tests', state='known', value=True, qualifiers=['Old revision']),
        ])
        self.contract = dict(schema_version=1, question_id='integration', question='Can revision r2 be integrated?',
                             subject='r2', source_sha256='', max_source_bytes=65536, max_result_bytes=4096,
                             requirements=[dict(id='change', purpose='answer'), dict(id='tests', purpose='guard')])

    def run_contract(self, document=None, contract=None, source_bytes=None):
        raw = source_bytes if source_bytes is not None else E.encode(self.document if document is None else document)
        self.source.write_bytes(raw)
        question = copy.deepcopy(self.contract if contract is None else contract)
        question['source_sha256'] = E.digest(raw)
        self.question.write_bytes(E.encode(question))
        return R.read_requirements(self.question, E.digest(self.question.read_bytes()), self.source)

    def assert_no_partial(self, result, status):
        self.assertEqual(result['status'], status, result)
        self.assertNotIn('requirements', result)
        self.assertNotIn('observations', result)

    def test_all_required_values_and_qualifiers_are_preserved(self):
        result = self.run_contract()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['scope'], 'declared_requirements_only')
        self.assertEqual(result['requirements'], [dict(req, observations=[self.document['observations'][i]])
                                                for i, req in enumerate(self.contract['requirements'])])
        self.assertEqual(result['source_sha256'], E.digest(self.source.read_bytes()))
        self.assertEqual(result['question_sha256'], E.digest(self.question.read_bytes()))
        self.assertEqual(result['metrics'], dict(source_reads=1, source_bytes_read=self.source.stat().st_size,
                                                question_reads=1, question_bytes_read=self.question.stat().st_size))

    def test_negative_zero_and_empty_values_are_observations_not_approval(self):
        for value in [False, 0, '', [], {}, {'status': 'failed'}]:
            with self.subTest(value=value):
                self.document['observations'][1]['value'] = value
                result = self.run_contract()
                self.assertEqual(result['status'], 'OBSERVED')
                self.assertEqual(E.encode(result['requirements'][1]['observations'][0]['value']), E.encode(value))

    def test_missing_renamed_or_other_subject_cannot_use_successful_receipt(self):
        for mutation in [('subject', 'r3'), ('requirement', 'test_results')]:
            document = copy.deepcopy(self.document)
            document['observations'][1][mutation[0]] = mutation[1]
            result = self.run_contract(document=document)
            self.assert_no_partial(result, 'INSUFFICIENT')
            self.assertEqual(result['gaps'], [dict(id='tests', reason='MISSING')])
        self.assert_no_partial(self.run_contract(document=dict(schema_version=1, observations=[])), 'INSUFFICIENT')

    def test_unknown_or_null_is_insufficient_even_with_known_record(self):
        for state in ['known', 'unknown']:
            document = copy.deepcopy(self.document)
            document['observations'].append(dict(document['observations'][1], id='unresolved', state=state, value=None))
            result = self.run_contract(document=document)
            self.assert_no_partial(result, 'INSUFFICIENT')
            self.assertEqual(result['gaps'], [dict(id='tests', reason='UNKNOWN')])

    def test_conflicting_values_are_not_resolved_by_order_or_success(self):
        document = copy.deepcopy(self.document)
        document['observations'].append(dict(document['observations'][1], id='opposite', value=True))
        for records in [document['observations'], list(reversed(document['observations']))]:
            result = self.run_contract(document=dict(schema_version=1, observations=records))
            self.assert_no_partial(result, 'INSUFFICIENT')
            self.assertEqual(result['gaps'], [dict(id='tests', reason='CONFLICT')])

    def test_conflicts_preserve_json_types_and_ignore_object_key_order(self):
        for left, right, expected in [(False, 0, 'INSUFFICIENT'), (1, 1.0, 'INSUFFICIENT'),
                                      ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}, 'OBSERVED')]:
            document = copy.deepcopy(self.document)
            document['observations'][1]['value'] = left
            document['observations'].append(dict(document['observations'][1], id='second', value=right))
            self.assertEqual(self.run_contract(document=document)['status'], expected)

    def test_equal_records_keep_every_id_qualifier_and_source_order(self):
        document = copy.deepcopy(self.document)
        extra = dict(document['observations'][1], id='second', qualifiers=['Not an independent execution'])
        document['observations'].insert(0, extra)
        result = self.run_contract(document=document)
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['requirements'][1]['observations'], [extra, self.document['observations'][1]])

    def test_duplicate_ids_and_sender_coverage_claims_are_refused(self):
        for document in [dict(self.document, declared_complete=True),
                         dict(self.document, observations=self.document['observations']*2)]:
            self.assert_no_partial(self.run_contract(document=document), 'REFUSED')

    def test_all_source_rows_are_validated_even_when_not_selected(self):
        for changes in [dict(state='unknown', value=True), dict(state=True), dict(qualifiers='limit'),
                        dict(qualifiers=[None]), dict(subject=''), dict(extra='ignored?')]:
            document = copy.deepcopy(self.document)
            document['observations'][2].update(changes)
            self.assert_no_partial(self.run_contract(document=document), 'REFUSED')

    def test_question_requires_unique_answer_and_guard_ids(self):
        rows = self.contract['requirements']
        for requirements in [[], rows[:1], rows[1:], rows*2, [dict(rows[0], purpose=True), rows[1]],
                             [dict(rows[0], id='bad name'), rows[1]]]:
            self.assert_no_partial(self.run_contract(contract=dict(self.contract, requirements=requirements)), 'REFUSED')
        requirements = [dict(id=f'field-{i}', purpose='guard' if i else 'answer') for i in range(33)]
        self.assert_no_partial(self.run_contract(contract=dict(self.contract, requirements=requirements)), 'REFUSED')

    def test_strict_question_schema_and_integer_bounds(self):
        for changes in [dict(schema_version=True), dict(question=' '), dict(question=[]), dict(subject=''),
                        dict(extra='ignored?'), dict(max_source_bytes=True), dict(max_result_bytes=0),
                        dict(max_source_bytes=4194305)]:
            result = self.run_contract(contract=dict(self.contract, **changes))
            self.assert_no_partial(result, 'REFUSED')
            self.assertEqual(result['metrics']['source_reads'], 0)

    def test_independently_pinned_question_and_source(self):
        self.run_contract()
        for digest in ['0'*64, 'invalid']:
            result = R.read_requirements(self.question, digest, self.source)
            self.assert_no_partial(result, 'REFUSED')
            self.assertEqual(result['metrics']['source_reads'], 0)
        digest = E.digest(self.question.read_bytes())
        self.source.write_bytes(self.source.read_bytes()+b' ')
        self.assert_no_partial(R.read_requirements(self.question, digest, self.source), 'REFUSED')

    def test_byte_bounds_refuse_instead_of_truncating(self):
        result = self.run_contract(contract=dict(self.contract, max_source_bytes=16))
        self.assert_no_partial(result, 'REFUSED')
        self.assertEqual(result['metrics']['source_bytes_read'], 17)
        self.assert_no_partial(self.run_contract(contract=dict(self.contract, max_result_bytes=16)), 'REFUSED')
        self.question.write_bytes(b' '*(E.REQUEST_LIMIT+1))
        result = R.read_requirements(self.question, E.digest(self.question.read_bytes()), self.source)
        self.assert_no_partial(result, 'REFUSED')
        self.assertEqual(result['metrics']['source_reads'], 0)

    def test_duplicate_json_keys_and_lossy_numbers_are_refused(self):
        for raw in [b'{"schema_version":1,"schema_version":1,"observations":[]}',
                    b'{"number":0.123456789012345678901}', b'{"number":1e-999}', b'{"number":NaN}', b'\xff']:
            self.assert_no_partial(self.run_contract(source_bytes=raw), 'REFUSED')
            self.question.write_bytes(raw)
            result = R.read_requirements(self.question, E.digest(raw), self.source)
            self.assert_no_partial(result, 'REFUSED')
            self.assertEqual(result['metrics']['source_reads'], 0)

    def test_missing_or_directory_sources_are_refused(self):
        self.run_contract()
        for path in [self.root/'missing', self.root]:
            self.assert_no_partial(R.read_requirements(self.question, E.digest(self.question.read_bytes()), path), 'REFUSED')

    def test_cli_is_read_only_and_uses_three_distinct_exit_codes(self):
        for module in [E, R]:
            shutil.copyfile(module.__file__, self.root/Path(module.__file__).name)
        for missing, wrong_pin, code, status in [(False, False, 0, 'OBSERVED'), (True, False, 1, 'INSUFFICIENT'),
                                                 (False, True, 2, 'REFUSED')]:
            document = dict(schema_version=1, observations=[]) if missing else self.document
            self.run_contract(document=document)
            before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
            digest = '0'*64 if wrong_pin else E.digest(self.question.read_bytes())
            result = subprocess.run([sys.executable, '-E', str(self.root/'read_requirements.py'),
                                     '--question', str(self.question), '--sha256', digest, '--source', str(self.source)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], status)
            self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_documented_command_preserves_limitations(self):
        repo = Path(__file__).resolve().parent.parent
        doc = (repo/'docs/requirement-selection.md').read_text(encoding='utf-8')
        command = re.search(r'^python tools/read_requirements.py .+$', doc, re.M).group()
        arguments = shlex.split(command); arguments[0] = sys.executable
        result = subprocess.run(arguments, cwd=repo, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'OBSERVED')
        self.assertIn('Root must check actual release before a real handoff',
                      report['requirements'][-1]['observations'][0]['qualifiers'])


if __name__ == '__main__':
    unittest.main()
