"""Required-check evidence is distinct from a successful watcher process."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import check_ci_snapshot as C

FIXTURES=Path(__file__).resolve().parent/'fixtures'


class CiSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((FIXTURES/'ci_policy.json').read_text(encoding='utf-8'))
        self.snapshot=json.loads((FIXTURES/'ci_snapshot.json').read_text(encoding='utf-8'))

    def check(self):
        return C.evaluate(self.policy,self.snapshot)

    def blocked(self,code):
        result=self.check()
        self.assertFalse(result['passes_required_checks'])
        self.assertIn(code,[b['code'] for b in result['blocking']])

    def test_successful_fixture_and_input_digests(self):
        p,s=json.dumps(self.policy).encode(),json.dumps(self.snapshot).encode()
        result=C.check(p,s)
        self.assertTrue(result['passes_required_checks'])
        self.assertEqual(result['passing_required'],2)
        self.assertEqual(result['policy_sha256'],hashlib.sha256(p).hexdigest())
        self.assertEqual(result['snapshot_sha256'],hashlib.sha256(s).hexdigest())

    def test_every_non_success_conclusion_is_blocked(self):
        for value in ('cancelled','failure','skipped','neutral','timed_out','stale','action_required','future_conclusion',None):
            with self.subTest(value=value):
                self.snapshot['check_runs'][0]['conclusion']=value
                self.blocked('REQUIRED_CHECK_NOT_SUCCESSFUL')

    def test_nonterminal_status_with_success_is_not_completed_evidence(self):
        for value in ('queued','in_progress','waiting','pending','requested','unknown'):
            with self.subTest(value=value):
                self.snapshot['check_runs'][0]['status']=value
                self.blocked('REQUIRED_CHECK_NOT_COMPLETED')

    def test_exact_full_revision_including_optional_rows(self):
        self.snapshot['check_runs'][0]['head_sha']='b'*40
        self.blocked('HEAD_MISMATCH')
        self.snapshot['check_runs'][0]['name']='optional'
        self.blocked('HEAD_MISMATCH')
        self.policy['expected_head']='a'*39
        with self.assertRaises(ValueError): self.check()

    def test_required_identity_is_name_and_app_id(self):
        self.snapshot['check_runs'][0]['app']['id']=99
        self.blocked('MISSING_REQUIRED_CHECK')
        self.setUp()
        self.snapshot['check_runs'][0]['name']='Unit Tests'
        self.blocked('MISSING_REQUIRED_CHECK')
        self.setUp()
        # Identically named optional output from another app cannot shadow or
        # invalidate the independently specified required app's successful run.
        extra=copy.deepcopy(self.snapshot['check_runs'][0])
        extra.update(id=3,app={'id':99},conclusion='failure')
        self.snapshot['check_runs'].append(extra);self.snapshot['total_count']+=1
        self.assertTrue(self.check()['passes_required_checks'])
        self.policy['required_checks'].append(dict(name=extra['name'],app_id=99))
        self.blocked('REQUIRED_CHECK_NOT_SUCCESSFUL')

    def test_missing_and_ambiguous_required_results(self):
        self.snapshot['check_runs'].pop();self.snapshot['total_count']-=1
        self.blocked('MISSING_REQUIRED_CHECK')
        for conclusion in ('success','cancelled'):
            self.setUp()
            row=dict(self.snapshot['check_runs'][0],id=3,conclusion=conclusion)
            self.snapshot['check_runs'].append(row);self.snapshot['total_count']+=1
            with self.subTest(conclusion=conclusion): self.blocked('AMBIGUOUS_REQUIRED_CHECK')

    def test_declared_count_does_not_allow_partial_or_overfull_snapshots(self):
        for total in (1,3):
            self.snapshot['total_count']=total
            with self.subTest(total=total): self.blocked('SNAPSHOT_COUNT_MISMATCH')
        self.snapshot.update(total_count=0,check_runs=[])
        self.blocked('MISSING_REQUIRED_CHECK')

    def test_optional_failure_and_provider_extensions_are_allowed(self):
        original=copy.deepcopy(self.snapshot)
        for status,conclusion in [('completed','failure'),('in_progress',None)]:
            self.snapshot=copy.deepcopy(original)
            self.snapshot['check_runs'].append(dict(id=3,name='optional',head_sha='a'*40,
                status=status,conclusion=conclusion,app={'id':42,'extra':'kept'},provider_extra=True))
            self.snapshot.update(total_count=3,provider_extra=True)
            result=self.check()
            self.assertTrue(result['passes_required_checks']);self.assertEqual(result['optional_checks'],1)

    def test_invalid_policy_fields_do_not_silently_weaken_requirements(self):
        changes=[dict(required_checks=[]),dict(schema_version=True),dict(expected_head='HEAD'),dict(extra=True),
                 dict(required_checks=[{'name':'unit tests','app_id':True}]),dict(required_checks=self.policy['required_checks']*2)]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                C.evaluate(dict(self.policy,**change),self.snapshot)

    def test_invalid_provider_fields_and_duplicate_run_ids(self):
        for field,value in [('total_count',True),('check_runs',{}),('total_count',-1)]:
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                C.evaluate(self.policy,dict(self.snapshot,**{field:value}))
        for field,value in [('id',True),('name',''),('head_sha','HEAD'),('status',None),('conclusion',False),('app',None),('app',{'id':True})]:
            changed=copy.deepcopy(self.snapshot);changed['check_runs'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError): C.evaluate(self.policy,changed)
        self.snapshot['check_runs'][1]['id']=self.snapshot['check_runs'][0]['id']
        with self.assertRaises(ValueError): self.check()

    def test_json_duplicates_and_nonfinite_values_are_rejected(self):
        p=json.dumps(self.policy).encode()
        for data in (b'{"total_count":0,"total_count":2,"check_runs":[]}',b'{"total_count":NaN,"check_runs":[]}',b'[]'):
            with self.subTest(data=data),self.assertRaises(ValueError): C.check(p,data)

    def test_order_and_inputs_are_preserved(self):
        before=copy.deepcopy(self.snapshot)
        self.check();self.assertEqual(before,self.snapshot)
        self.snapshot['check_runs'].reverse()
        self.assertTrue(self.check()['passes_required_checks'])

    def test_cli_exit_codes_and_readonly_without_cache_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('check_ci_snapshot.py','check_comparison.py'):
                shutil.copyfile(Path(C.__file__).with_name(name),root/name)
            policy,snapshot=root/'policy.json',root/'snapshot.json'
            policy.write_text(json.dumps(self.policy),encoding='utf-8')
            snapshot.write_text(json.dumps(self.snapshot),encoding='utf-8')
            command=[sys.executable,'-E',str(root/'check_ci_snapshot.py'),'--policy',str(policy),'--snapshot',str(snapshot)]
            before={p.name:p.read_bytes() for p in root.iterdir()}
            def run():
                result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
                return result.returncode,json.loads(result.stdout)
            code,report=run();self.assertEqual(code,0);self.assertTrue(report['passes_required_checks'])
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.snapshot['check_runs'][0]['conclusion']='cancelled'
            snapshot.write_text(json.dumps(self.snapshot),encoding='utf-8')
            code,report=run();self.assertEqual(code,1);self.assertFalse(report['passes_required_checks'])
            snapshot.write_text('[]',encoding='utf-8')
            code,report=run();self.assertEqual(code,2);self.assertFalse(report['passes_required_checks'])


if __name__=='__main__':
    unittest.main()
