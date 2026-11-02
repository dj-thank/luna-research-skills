import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import check_comparison as C
import inspect_comparison_run as I

FIXTURES=Path(__file__).resolve().parent/'fixtures'


class RecoveryInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.raw=(FIXTURES/'comparison_evidence.json').read_bytes()
        self.report=(FIXTURES/'comparison_report.json').read_bytes()
        self.pin=hashlib.sha256(self.raw).hexdigest()

    def make_run(self,name='run',location='accepted',raw=None):
        run=self.root/name;bundle=run/location;bundle.mkdir(parents=True)
        data=self.raw if raw is None else raw;pin=hashlib.sha256(data).hexdigest()
        (bundle/'evidence.json').write_bytes(data)
        (bundle/'evidence.sha256').write_text(pin+'\n',encoding='utf-8')
        report=self.report if raw is None else json.dumps(C.summarize(C.load_json(data),pin)).encode()
        (bundle/'report.json').write_bytes(report)
        return run,bundle,pin

    def snapshot(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_complete_published_and_input_fingerprints_without_writes(self):
        run,bundle,pin=self.make_run();before=self.snapshot()
        result=I.inspect_run(run,pin)
        self.assertEqual(result['state'],'COMPLETE_PUBLISHED');self.assertTrue(result['published'])
        self.assertEqual(result['artifact_sha256']['evidence.json'],pin)
        self.assertEqual(result['artifact_sha256']['report.json'],hashlib.sha256(self.report).hexdigest())
        self.assertEqual(before,self.snapshot())

    def test_complete_staging_is_not_published(self):
        run,_,pin=self.make_run(location='.pending')
        result=I.inspect_run(run,pin)
        self.assertEqual(result['state'],'COMPLETE_STAGED');self.assertTrue(result['complete']);self.assertFalse(result['published'])

    def test_valid_negative_comparison_is_complete_evidence(self):
        document=C.load_json(self.raw)
        for case in document['cases']:case['choices']['candidate']=case['choices']['baseline']
        raw=json.dumps(document).encode()
        run,_,pin=self.make_run(raw=raw)
        result=I.inspect_run(run,pin)
        self.assertTrue(result['complete']);self.assertFalse(result['passes_case_gate'])

    def test_missing_empty_and_legacy_layout_do_not_become_complete(self):
        absent=self.root/'absent'
        self.assertEqual(I.inspect_run(absent,self.pin)['state'],'INCOMPLETE');self.assertFalse(absent.exists())
        empty=self.root/'empty';empty.mkdir()
        self.assertFalse(I.inspect_run(empty,self.pin)['complete'])
        run,_,pin=self.make_run(location='')
        self.assertEqual(I.inspect_run(run,pin)['reason'],'NO_KNOWN_BUNDLE')

    def test_missing_artifacts_precede_content_checks(self):
        for index,name in enumerate(I.ARTIFACTS):
            run,bundle,pin=self.make_run(str(index))
            (bundle/name).unlink()
            result=I.inspect_run(run,pin)
            self.assertEqual(result['state'],'INCOMPLETE');self.assertEqual(result['missing'],[name])

    def test_two_locations_are_ambiguous_even_with_a_valid_copy(self):
        run,bundle,pin=self.make_run();(run/'.pending').mkdir()
        self.assertEqual(I.inspect_run(run,pin)['state'],'CONFLICT')
        for name in I.ARTIFACTS:shutil.copyfile(bundle/name,run/'.pending'/name)
        self.assertEqual(I.inspect_run(run,pin)['reason'],'AMBIGUOUS_LOCATIONS')

    def test_independent_pin_sidecar_and_report_must_all_agree(self):
        run,bundle,pin=self.make_run('caller')
        self.assertFalse(I.inspect_run(run,'0'*64)['complete'])
        for index,(name,data) in enumerate([('evidence.sha256',b'0'*64),('evidence.sha256',b'\xff'),
                ('evidence.json',self.raw+b' '),('report.json',b'{}')]):
            run,bundle,pin=self.make_run(str(index));(bundle/name).write_bytes(data)
            with self.subTest(name=name):self.assertEqual(I.inspect_run(run,pin)['state'],'CONFLICT')

    def test_report_is_mandatory_not_an_optional_null_argument(self):
        for index,data in enumerate((b'null',b'false',b'[]',b'{',b'{"schema_version":1,"schema_version":1}')):
            run,bundle,pin=self.make_run(str(index));(bundle/'report.json').write_bytes(data)
            with self.subTest(data=data):self.assertEqual(I.inspect_run(run,pin)['state'],'CONFLICT')

    def test_types_and_detected_reparse_or_special_nodes_are_not_read(self):
        run,bundle,pin=self.make_run()
        original=Path.lstat
        for mode,attributes in ((stat.S_IFLNK,0),(stat.S_IFIFO,0),(stat.S_IFREG,0x400)):
            def metadata(path,*,_mode=mode,_attributes=attributes):
                if path==bundle/'report.json':return SimpleNamespace(st_mode=_mode,st_file_attributes=_attributes)
                return original(path)
            with mock.patch.object(Path,'lstat',metadata),mock.patch.object(Path,'read_bytes',side_effect=AssertionError('unsafe read')):
                self.assertEqual(I.inspect_run(run,pin)['state'],'CONFLICT')
        invalid=self.root/'invalid';invalid.mkdir();(invalid/'accepted').write_bytes(b'file')
        self.assertEqual(I.inspect_run(invalid,pin)['reason'],'INVALID_LOCATION_TYPE')

    def test_real_link_is_rejected_without_reading_its_target(self):
        _,target,pin=self.make_run('target');run=self.root/'linked';run.mkdir()
        try:(run/'accepted').symlink_to(target,target_is_directory=True)
        except OSError as exc:self.skipTest(f'symlink creation unavailable: {exc}')
        with mock.patch.object(Path,'read_bytes',side_effect=AssertionError('followed link')):
            self.assertEqual(I.inspect_run(run,pin)['state'],'CONFLICT')

    def test_bad_arguments_and_read_errors_are_errors_not_incomplete_results(self):
        run,_,pin=self.make_run()
        for bad in ('HEAD','A'*64,True):
            with self.subTest(pin=bad),self.assertRaises(ValueError):I.inspect_run(run,bad)
        not_directory=self.root/'file';not_directory.write_bytes(b'x')
        with self.assertRaises(ValueError):I.inspect_run(not_directory,pin)
        output=io.StringIO()
        with mock.patch.object(Path,'read_bytes',side_effect=PermissionError('unreadable')),contextlib.redirect_stdout(output):
            self.assertEqual(I.main(['--run',str(run),'--sha256',pin]),2)
        self.assertEqual(json.loads(output.getvalue())['state'],'ERROR')

    def test_packaged_cli_exit_codes_and_readonly_with_python_E(self):
        run,_,pin=self.make_run()
        for name in ('inspect_comparison_run.py','check_comparison.py'):
            shutil.copyfile(Path(I.__file__).with_name(name),self.root/name)
        before=self.snapshot()
        for path,digest,expected in [(run,pin,0),(self.root/'absent',pin,1),(run,'HEAD',2)]:
            result=subprocess.run([sys.executable,'-E',str(self.root/'inspect_comparison_run.py'),'--run',str(path),'--sha256',digest],cwd=self.root,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,expected,result.stderr)
            self.assertEqual(json.loads(result.stdout)['complete'],expected==0)
        self.assertEqual(before,self.snapshot())


if __name__=='__main__':unittest.main()
