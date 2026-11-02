"""Execute the documented publication recipe, including abrupt process exits."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import check_comparison as C

ROOT=Path(__file__).resolve().parent.parent


class ComparisonDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        tools=self.root/'tools';(tools/'fixtures').mkdir(parents=True)
        for name in ('export_review_comparison.py','benchmark_review.py','benchmark_swarm.py','check_comparison.py'):
            shutil.copyfile(ROOT/'tools'/name,tools/name)
        shutil.copyfile(ROOT/'tools/fixtures/review_benchmark.json',tools/'fixtures/review_benchmark.json')
        blocks=re.findall(r'```python\n(.*?)\n```',(ROOT/'docs/comparison-reports.md').read_text(encoding='utf-8'),re.S)
        self.assertEqual(len(blocks),1)
        (self.root/'recipe.py').write_text(blocks[0]+'\n',encoding='utf-8')
        self.run_dir=self.root/'work/review-export'

    def execute(self,wrapper=None):
        script=self.root/'recipe.py'
        if wrapper:
            script=self.root/'fault.py';script.write_text(wrapper,encoding='utf-8')
        return subprocess.run([sys.executable,'-E',str(script)],cwd=self.root,capture_output=True,timeout=30)

    def valid(self,folder):
        raw=(folder/'evidence.json').read_bytes()
        pin=(folder/'evidence.sha256').read_text(encoding='utf-8').strip()
        self.assertEqual(pin,hashlib.sha256(raw).hexdigest())
        self.assertTrue(C.check(raw,pin,C.load_json((folder/'report.json').read_bytes()))['consistent'])

    def test_success_publishes_a_complete_bundle_and_refuses_existing_run(self):
        result=self.execute();self.assertEqual(result.returncode,0,result.stderr)
        self.valid(self.run_dir/'accepted');self.assertFalse((self.run_dir/'.pending').exists())
        before={str(p.relative_to(self.run_dir)):p.read_bytes() for p in self.run_dir.rglob('*') if p.is_file()}
        self.assertNotEqual(self.execute().returncode,0)
        self.assertEqual(before,{str(p.relative_to(self.run_dir)):p.read_bytes() for p in self.run_dir.rglob('*') if p.is_file()})

    def test_producer_refusal_keeps_audit_without_publishing(self):
        fixture=self.root/'tools/fixtures/review_benchmark.json'
        fixture.write_bytes(fixture.read_bytes()+b'\n')
        self.assertNotEqual(self.execute().returncode,0)
        self.assertFalse((self.run_dir/'accepted').exists())
        audit=json.loads((self.run_dir/'.pending/producer-audit.json').read_bytes())
        self.assertFalse(audit['complete']);self.assertEqual(audit['attempted_calls'],0)

    def test_abrupt_partial_write_does_not_publish(self):
        result=self.execute('''import os, pathlib, runpy
original = pathlib.Path.open
class Interrupted:
    def __init__(self, stream): self.stream = stream
    def __enter__(self): return self
    def __exit__(self, *args): self.stream.close()
    def write(self, data):
        self.stream.write(data[:len(data)//2]); self.stream.flush(); os._exit(73)
def opened(path, *args, **kwargs):
    stream = original(path, *args, **kwargs)
    if path.name == 'evidence.json' and args == ('xb',): return Interrupted(stream)
    return stream
pathlib.Path.open = opened
runpy.run_path('recipe.py', run_name='__main__')
''')
        self.assertEqual(result.returncode,73,result.stderr)
        self.assertFalse((self.run_dir/'accepted').exists())
        partial=self.run_dir/'.pending/evidence.json'
        self.assertGreater(partial.stat().st_size,0)
        with self.assertRaises(ValueError): C.load_json(partial.read_bytes())

    def test_before_publication_leaves_a_recoverable_staged_bundle(self):
        result=self.execute('''import os, pathlib, runpy
def interrupted(path, target): os._exit(74)
pathlib.Path.rename = interrupted
runpy.run_path('recipe.py', run_name='__main__')
''')
        self.assertEqual(result.returncode,74,result.stderr)
        self.assertFalse((self.run_dir/'accepted').exists());self.valid(self.run_dir/'.pending')

    def test_lost_acknowledgement_does_not_invalidate_published_bytes(self):
        result=self.execute('''import os, pathlib, runpy
original = pathlib.Path.rename
def interrupted(path, target):
    original(path, target); os._exit(75)
pathlib.Path.rename = interrupted
runpy.run_path('recipe.py', run_name='__main__')
''')
        self.assertEqual(result.returncode,75,result.stderr)
        self.valid(self.run_dir/'accepted');self.assertFalse((self.run_dir/'.pending').exists())


if __name__=='__main__': unittest.main()
