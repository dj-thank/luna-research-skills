import copy
import json
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import read_evidence as R


class ReadEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.json'
        self.request = self.root / 'request.json'
        self.document = {'answer': 'candidate', 'guard': {'accepted': False, 'limits': ['LOCAL_PASS only']},
                         'unrelated': 'kept in the original source', 'list': [None, False, 3],
                         'a/b': {'~1': '正解'}, '': 'empty key'}
        self.contract = dict(schema_version=1, source_sha256='', max_source_bytes=65536, max_result_bytes=4096,
                             selections=[dict(id='answer', purpose='answer', pointer='/answer'),
                                         dict(id='guard', purpose='guard', pointer='/guard')])
        self.save_source(R.encode(self.document))

    def save_source(self, data):
        self.source.write_bytes(data)
        self.contract['source_sha256'] = R.digest(data)

    def run_contract(self, contract=None):
        self.request.write_bytes(R.encode(self.contract if contract is None else contract))
        return R.read_evidence(self.request, R.digest(self.request.read_bytes()), self.source)

    def assert_refused(self, result):
        self.assertEqual(result['status'], 'REFUSED', result)
        self.assertNotIn('values', result)

    def test_exact_partial_view_keeps_negative_guards_and_provenance(self):
        before = self.source.read_bytes()
        result = self.run_contract()
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['scope'], 'selected_fields_only')
        self.assertEqual([r['value'] for r in result['values']], [self.document['answer'], self.document['guard']])
        self.assertEqual(result['source_sha256'], R.digest(before))
        self.assertEqual(result['request_sha256'], R.digest(self.request.read_bytes()))
        self.assertEqual(result['metrics'], dict(request_reads=1, request_bytes_read=self.request.stat().st_size,
                                                 source_reads=1, source_bytes_read=len(before)))
        self.assertEqual(self.source.read_bytes(), before)
        self.assertNotIn('unrelated', R.encode(result).decode())

    def test_source_and_request_pins_are_independent(self):
        self.run_contract()
        request_pin = R.digest(self.request.read_bytes())
        self.source.write_bytes(self.source.read_bytes() + b' ')
        self.assert_refused(R.read_evidence(self.request, request_pin, self.source))
        self.contract['source_sha256'] = R.digest(self.source.read_bytes())
        self.request.write_bytes(R.encode(self.contract))
        result = R.read_evidence(self.request, request_pin, self.source)
        self.assert_refused(result)
        self.assertEqual(result['metrics']['source_reads'], 0)

    def test_missing_guard_refuses_the_entire_view(self):
        self.contract['selections'][1]['pointer'] = '/missing'
        self.assert_refused(self.run_contract())

    def test_schema_refusals_before_source_read(self):
        variants = [None, [], {}, dict(self.contract, schema_version=True), dict(self.contract, schema_version=2),
                    dict(self.contract, max_source_bytes=True), dict(self.contract, max_source_bytes=0),
                    dict(self.contract, max_result_bytes=R.DOCUMENT_LIMIT+1), dict(self.contract, source_sha256='x'),
                    dict(self.contract, auto_publish=True), dict(self.contract, selections=[]),
                    dict(self.contract, selections=[self.contract['selections'][0]]),
                    dict(self.contract, selections=[self.contract['selections'][1]])]
        for value in variants:
            with self.subTest(value=value):
                self.request.write_bytes(R.encode(value))
                result = R.read_evidence(self.request, R.digest(self.request.read_bytes()), self.source)
                self.assert_refused(result)
                self.assertEqual(result['metrics']['source_reads'], 0)

    def test_selection_shape_ids_duplicates_and_roles(self):
        for change in [dict(id='answer'), dict(pointer='/answer'), dict(purpose='approval'), dict(id=True),
                       dict(pointer=3), dict(pointer='#/guard'), dict(pointer='/bad~2'), dict(extra='ignored')]:
            contract = copy.deepcopy(self.contract)
            contract['selections'][1].update(change)
            with self.subTest(change=change):
                result = self.run_contract(contract)
                self.assert_refused(result)
                self.assertEqual(result['metrics']['source_reads'], 0)

    def test_actual_read_budgets_include_only_one_overflow_probe(self):
        size = self.source.stat().st_size
        self.contract['max_source_bytes'] = size - 2
        result = self.run_contract()
        self.assert_refused(result)
        self.assertEqual(result['metrics']['source_reads'], 1)
        self.assertEqual(result['metrics']['source_bytes_read'], size - 1)
        self.request.write_bytes(b' ' * (R.REQUEST_LIMIT+2))
        result = R.read_evidence(self.request, R.digest(self.request.read_bytes()), self.source)
        self.assert_refused(result)
        self.assertEqual(result['metrics']['request_bytes_read'], R.REQUEST_LIMIT+1)
        self.assertEqual(result['metrics']['source_reads'], 0)

    def test_result_budget_refuses_without_truncation(self):
        self.contract['max_result_bytes'] = 1
        self.assert_refused(self.run_contract())

    def test_pointer_escapes_empty_key_root_and_typed_values(self):
        for pointer, expected in [('', self.document), ('/', 'empty key'), ('/a~1b/~01', '正解'),
                                  ('/list/0', None), ('/list/1', False), ('/list/2', 3)]:
            with self.subTest(pointer=pointer):
                self.assertEqual(R.select(self.document, pointer), expected)
                self.assertIs(type(R.select(self.document, pointer)), type(expected))

    def test_invalid_or_missing_pointer_has_no_default(self):
        for pointer in ['/list/-', '/list/01', '/list/-1', '/list/3', '/list/9999999999999999999999',
                        '/answer/nested', '/missing', '/bad~', 'answer', '#/answer']:
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                R.select(self.document, pointer)

    def test_strict_json_for_sources_and_requests(self):
        for data in [b'{', b'{"answer":1,"answer":2}', b'{"answer":NaN}', b'{"answer":Infinity}',
                     b'{"answer":1e999}', b'\xff', '{"answer":1}'.encode('utf-16')]:
            with self.subTest(data=data):
                self.save_source(data)
                self.assert_refused(self.run_contract())
                self.request.write_bytes(data)
                result = R.read_evidence(self.request, R.digest(data), self.source)
                self.assert_refused(result)
                self.assertEqual(result['metrics']['source_reads'], 0)

    def test_numbers_cannot_silently_lose_decimal_precision(self):
        for literal in ['0.123456789012345678901', '1e-999']:
            self.save_source(('{"answer":'+literal+',"guard":false}').encode())
            self.assert_refused(self.run_contract())
        self.save_source(b'{"answer":1.25,"guard":false}')
        result = self.run_contract()
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['values'][0]['value'], 1.25)

    def test_nonregular_and_reparse_leaf_refused_before_open(self):
        for mode, attrs in [(stat.S_IFIFO, 0), (stat.S_IFLNK, 0), (stat.S_IFREG, 0x400)]:
            with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_file_attributes=attrs)), \
                    patch.object(Path, 'open', side_effect=AssertionError('must not open')):
                self.assert_refused(R.read_evidence(self.request, '0'*64, self.source))

    def test_missing_directory_and_read_error(self):
        self.run_contract()
        for path in [self.root/'missing', self.root]:
            self.assert_refused(R.read_evidence(self.request, R.digest(self.request.read_bytes()), path))
        with patch.object(Path, 'open', side_effect=PermissionError('blocked')):
            self.assert_refused(R.read_evidence(self.request, '0'*64, self.source))

    def test_cli_read_only_in_copied_directory_and_exit_codes(self):
        self.run_contract()
        script = self.root/'read_evidence.py'
        shutil.copyfile(R.__file__, script)
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        for digest, code in [(R.digest(self.request.read_bytes()), 0), ('0'*64, 2), ('invalid', 2)]:
            run = subprocess.run([sys.executable, '-E', str(script), '--request', str(self.request), '--sha256', digest,
                                  '--source', str(self.source)], capture_output=True, timeout=10)
            self.assertEqual(run.returncode, code, run.stderr)
            self.assertEqual(json.loads(run.stdout)['status'], 'VERIFIED' if code==0 else 'REFUSED')
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_documented_command_keeps_pending_fixture_pending(self):
        repo = Path(__file__).resolve().parent.parent
        doc = (repo/'docs/on-demand-evidence.md').read_text(encoding='utf-8')
        command = re.search(r'^python tools/read_evidence.py .+$', doc, re.M).group()
        arguments = shlex.split(command)
        arguments[0] = sys.executable
        run = subprocess.run(arguments, cwd=repo, capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(next(v['value'] for v in result['values'] if v['id']=='status'), 'pending')


if __name__ == '__main__':
    unittest.main()
