import copy
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

import read_evidence as E
import read_requirements as R


class RequirementRelationTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parent.parent
        self.document = json.loads((self.repo/'tools/fixtures/relation_source.json').read_bytes())
        self.contract = json.loads((self.repo/'tools/fixtures/relation_question.json').read_bytes())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def value(self, name):
        return next(row['value'] for row in self.document['observations'] if row['requirement'] == name)

    def run_question(self):
        raw = E.encode(self.document)
        self.contract['source_sha256'] = E.digest(raw)
        question = E.encode(self.contract)
        (self.root/'source.json').write_bytes(raw)
        (self.root/'question.json').write_bytes(question)
        return R.read_requirements(self.root/'question.json', E.digest(question), self.root/'source.json')

    def assert_insufficient(self, result, gaps):
        self.assertEqual(result['status'], 'INSUFFICIENT', result)
        self.assertEqual({row['id']: row['reason'] for row in result['relation_gaps']}, gaps)
        self.assertNotIn('requirements', result)
        self.assertNotIn('relation_checks', result)

    def test_match_preserves_every_record_and_qualifier(self):
        extra = copy.deepcopy(self.document['observations'][1])
        extra.update(id='another-test-record', qualifiers=['Same values do not prove independent execution'])
        self.document['observations'].insert(0, extra)
        result = self.run_question()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['scope'], 'declared_requirements_and_relations_only')
        expected = [dict(req, observations=[row for row in self.document['observations'] if row['requirement'] == req['id']])
                    for req in self.contract['requirements']]
        self.assertEqual(E.encode(result['requirements']), E.encode(expected))
        self.assertEqual(len(result['relation_checks']), 5)
        self.assertTrue(all(row['status'] == 'MATCH' for row in result['relation_checks']))

    def test_mismatched_revision_artifact_and_scope_report_all_gaps(self):
        self.value('tests').update(revision='old', artifact='old-artifact', targets=['linux'])
        self.value('prerequisite')['artifact'] = 'unrelated-artifact'
        self.assert_insufficient(self.run_question(), {'test-revision': 'MISMATCH', 'test-artifact': 'MISMATCH',
                                                       'target-coverage': 'MISMATCH', 'prerequisite-artifact': 'MISMATCH'})

    def test_missing_and_null_operands_never_equal_successfully(self):
        self.value('tests').pop('revision')
        self.assert_insufficient(self.run_question(), {'test-revision': 'MISSING'})
        self.value('tests')['revision'] = None
        self.value('change')['revision'] = None
        self.assert_insufficient(self.run_question(), {'test-revision': 'UNKNOWN'})

    def test_subset_is_order_independent_and_allows_extras_duplicates_empty_requirement(self):
        for targets in [['linux', 'windows'], ['linux', 'windows', 'freebsd'], ['windows', 'linux', 'linux']]:
            self.value('tests')['targets'] = targets
            self.assertEqual(self.run_question()['status'], 'OBSERVED')
        self.value('change')['targets'] = []
        self.value('tests')['targets'] = []
        self.assertEqual(self.run_question()['status'], 'OBSERVED')

    def test_subset_rejects_wrong_shapes_and_does_not_normalize_labels(self):
        for targets in ['linux,windows', ['linux', False], {'linux': True}, ['Linux', 'windows']]:
            self.value('tests')['targets'] = targets
            reason = 'MISMATCH' if targets == ['Linux', 'windows'] else 'TYPE'
            self.assert_insufficient(self.run_question(), {'target-coverage': reason})

    def test_equal_is_typed_and_ignores_object_key_order(self):
        for left, right, status in [(False, 0, 'INSUFFICIENT'), (1, 1.0, 'INSUFFICIENT'),
                                    (False, False, 'OBSERVED'), ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}, 'OBSERVED')]:
            self.value('tests')['counter'] = left
            self.value('change')['counter'] = right
            self.assertEqual(self.run_question()['status'], status)

    def test_escaped_and_root_pointers_select_exact_values(self):
        self.value('tests')['a/b'] = {'~k': 'correct'}
        self.value('change')['a/b'] = {'~k': 'correct'}
        relation = copy.deepcopy(self.contract['relations'][0])
        relation['left']['pointer'] = relation['right']['pointer'] = '/a~1b/~0k'
        self.contract['relations'] = [relation]
        self.assertEqual(self.run_question()['status'], 'OBSERVED')
        self.value('tests').clear(); self.value('change').clear()
        relation['left']['pointer'] = relation['right']['pointer'] = ''
        self.assertEqual(self.run_question()['status'], 'OBSERVED')

    def test_unresolved_requirements_precede_relation_evaluation(self):
        self.document['observations'][1].update(state='unknown', value=None)
        result = self.run_question()
        self.assertEqual(result['status'], 'INSUFFICIENT')
        self.assertEqual(result['gaps'], [dict(id='tests', reason='UNKNOWN')])
        self.assertNotIn('relation_gaps', result)
        self.assertNotIn('relation_checks', result)
        self.assertNotIn('requirements', result)

    def test_invalid_relation_contracts_refuse_before_source_read(self):
        original = copy.deepcopy(self.contract)
        mutations = [
            lambda q: q.update(relations=[]),
            lambda q: q.update(relations=[dict(q['relations'][0], id=f'r{i}') for i in range(33)]),
            lambda q: q['relations'].append(q['relations'][0]),
            lambda q: q['relations'][0].update(operator='execute'),
            lambda q: q['relations'][0].update(operator=True),
            lambda q: q['relations'][0].update(ignore_failure=True),
            lambda q: q['relations'][0]['left'].update(requirement='not-declared'),
            lambda q: q['relations'][0]['left'].update(pointer='/bad~escape'),
            lambda q: q['relations'][0].update(right=q['relations'][0]['left']),
            lambda q: q.update(schema_version=1),
            lambda q: q.update(schema_version=2.0),
        ]
        for mutate in mutations:
            self.contract = copy.deepcopy(original); mutate(self.contract)
            result = self.run_question()
            self.assertEqual(result['status'], 'REFUSED', result)
            self.assertEqual(result['metrics']['source_reads'], 0)
            self.assertNotIn('requirements', result)

    def test_v1_still_returns_facts_without_a_relation_verdict(self):
        self.value('tests')['revision'] = 'old'
        self.contract['schema_version'] = 1
        del self.contract['relations']
        result = self.run_question()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['scope'], 'declared_requirements_only')
        self.assertEqual(result['requirements'][1]['observations'][0]['value']['revision'], 'old')
        self.assertNotIn('relation_checks', result)
        self.assertNotIn('relation_gaps', result)

    def test_relation_metadata_counts_against_output_bound(self):
        result = self.run_question()
        self.contract['max_result_bytes'] = len(E.encode(result))-1
        refused = self.run_question()
        self.assertEqual(refused['status'], 'REFUSED')
        self.assertNotIn('requirements', refused)
        self.assertNotIn('relation_checks', refused)

    def test_documented_v2_example_does_not_claim_acceptance(self):
        doc = (self.repo/'docs/requirement-selection.md').read_text(encoding='utf-8')
        command = re.search(r'^python tools/read_requirements.py --question tools/fixtures/relation_question.json .+$', doc, re.M).group()
        args = shlex.split(command); args[0] = sys.executable
        run = subprocess.run(args, cwd=self.repo, capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertIn('Root must review permission, freshness and all negative facts',
                      result['requirements'][-1]['observations'][0]['value'])


if __name__ == '__main__':
    unittest.main()
