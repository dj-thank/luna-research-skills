import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest


class ReceiverQuestionExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parent.parent
        doc = (cls.repo/'docs/receiver-questions.md').read_text(encoding='utf-8')
        cls.commands = re.findall(r'^python tools/read_requirements.py .+$', doc, re.M)

    def run_example(self, position, expected_code):
        self.assertEqual(len(self.commands), 2)
        command = shlex.split(self.commands[position]); command[0] = sys.executable
        run = subprocess.run(command, cwd=self.repo, capture_output=True, timeout=10)
        self.assertEqual(run.returncode, expected_code, run.stdout+run.stderr)
        result = json.loads(run.stdout)
        source = self.repo/'tools/fixtures/handoff_source.json'
        self.assertEqual(result['source_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
        return result

    def test_sender_matches_do_not_hide_revision_difference_or_approve_pending(self):
        result = self.run_example(0, 0)
        self.assertEqual(result['status'], 'OBSERVED')
        values = {row['id']: row['observations'][0]['value'] for row in result['requirements']}
        self.assertEqual(values['proposal']['revision'], 'q4')
        self.assertEqual(values['receipt']['revision'], 'q3')
        self.assertEqual(values['authorization']['status'], 'pending')
        self.assertEqual({row['id'] for row in result['relation_checks']}, {'target-coverage', 'authorized-artifact'})
        self.assertTrue(all(row['status']=='MATCH' for row in result['relation_checks']))

    def test_receiver_obligation_detects_mismatch_on_the_same_source(self):
        result = self.run_example(1, 1)
        self.assertEqual(result['status'], 'INSUFFICIENT')
        self.assertEqual(result['relation_gaps'], [dict(id='test-revision', reason='MISMATCH')])
        self.assertNotIn('requirements', result)
        self.assertNotIn('relation_checks', result)


if __name__ == '__main__':
    unittest.main()
