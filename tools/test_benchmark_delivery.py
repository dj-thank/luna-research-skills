"""Receiver-state and negative controls for bounded delivery recovery."""
import copy
from contextlib import closing
import json
import multiprocessing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark_delivery as D


def receive_overlapping(database, envelope, payload, start, empty_read, results):
    """Force the check-then-insert gap, but never block inside a transaction."""
    connect = sqlite3.connect

    class OverlapConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            cursor = super().execute(sql, parameters)
            if sql.startswith('SELECT payload FROM inbox') and not self.in_transaction:
                row = cursor.fetchone()
                cursor.close()
                if row is None:
                    empty_read.wait(timeout=10)
                return SimpleNamespace(fetchone=lambda: row)
            return cursor

    try:
        start.wait(timeout=10)
        with patch.object(D.sqlite3, 'connect', lambda db: connect(db, factory=OverlapConnection)):
            ack = D.receive(database, envelope, payload, envelope, dedup=True)
        results.put({'ack': ack, 'error': None})
    except Exception as exc:
        results.put({'ack': None, 'error': repr(exc)})


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(D.DEFAULT_CASES.read_text(encoding='utf-8'))

    def test_frozen_cli_keeps_failed_controls_and_finite_counts(self):
        before = D.DEFAULT_CASES.read_bytes()
        result = subprocess.run([sys.executable, D.__file__], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual((report['passed'], report['total']), (18, 18))
        self.assertEqual([report['metrics'][p]['correct'] for p in D.POLICIES], [3, 9, 18])
        self.assertEqual([report['metrics'][p]['attempts'] for p in D.POLICIES], [18, 35, 35])
        self.assertEqual([report['metrics'][p]['effect_count'] for p in D.POLICIES], [10, 26, 17])
        self.assertTrue(report['candidate_gate'])
        self.assertEqual(D.DEFAULT_CASES.read_bytes(), before)

    def test_every_data_and_ack_identity_field_is_bound(self):
        for prefix in ('data_', 'ack_'):
            for field in D.FIELDS:
                with self.subTest(prefix=prefix, field=field):
                    case = copy.deepcopy(self.doc['cases'][0])
                    case.update(faults=[prefix + field, 'ok'],
                                expected_policy_correct=dict(send_once=False, ack_retry=prefix == 'data_', ack_retry_dedup=True),
                                expected_attempts=dict(send_once=1, ack_retry=2, ack_retry_dedup=2))
                    report = D.run_benchmark(dict(self.doc, cases=[case]))
                    self.assertEqual(report['passed'], 1)
                    self.assertTrue(report['candidate_gate'])

    def test_rollback_keeps_receipt_and_effect_atomic(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'receiver.sqlite'
            envelope, payload = self.doc['envelope'], self.doc['payload'].encode('utf-8')
            self.assertIsNone(D.receive(db, envelope, payload, envelope, dedup=True, rollback=True))
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM inbox').fetchone()[0], 0)
                self.assertEqual(con.execute('SELECT count(*) FROM effects').fetchone()[0], 0)
            for _ in range(2):
                self.assertEqual(D.receive(db, envelope, payload, envelope, dedup=True), envelope)
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT payload FROM inbox').fetchall(), [(payload,)])
                self.assertEqual(con.execute('SELECT payload FROM effects').fetchall(), [(payload,)])

    def test_distinct_requests_with_equal_bytes_are_not_collapsed(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'receiver.sqlite'
            payload = self.doc['payload'].encode('utf-8')
            for delivery in ('first', 'second'):
                envelope = dict(self.doc['envelope'], delivery_id=delivery)
                self.assertEqual(D.receive(db, envelope, payload, envelope, dedup=True), envelope)
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM effects').fetchone()[0], 2)

    def test_two_processes_claim_receipts_without_duplicate_effects(self):
        ctx = multiprocessing.get_context('spawn')
        payload = self.doc['payload'].encode('utf-8')
        for scenario in ('same_empty', 'same_seeded', 'distinct', 'one_corrupt'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                db = Path(temp) / 'receiver.sqlite'
                envelopes = [dict(self.doc['envelope']) for _ in range(2)]
                bodies = [payload, payload]
                if scenario == 'distinct':
                    envelopes[1]['delivery_id'] += '-second'
                if scenario == 'one_corrupt':
                    bodies[1] += b'corrupt'
                # Isolate receipt contention from first-time schema creation.
                with closing(sqlite3.connect(db)) as con, con:
                    con.execute('CREATE TABLE inbox (identity TEXT PRIMARY KEY, payload BLOB NOT NULL)')
                    con.execute('CREATE TABLE effects (payload BLOB NOT NULL)')
                    if scenario == 'same_seeded':
                        con.execute('INSERT INTO inbox VALUES (?,?)', (json.dumps(envelopes[0], sort_keys=True), payload))
                        con.execute('INSERT INTO effects VALUES (?)', (payload,))
                start = ctx.Barrier(2)
                gap = ctx.Barrier(1 if scenario == 'one_corrupt' else 2)
                results = ctx.Queue()
                processes = [ctx.Process(target=receive_overlapping,
                    args=(db, envelopes[i], bodies[i], start, gap, results)) for i in range(2)]
                try:
                    deadline = time.monotonic() + 30
                    for process in processes:
                        process.start()
                    for process in processes:
                        process.join(timeout=max(0, deadline - time.monotonic()))
                    self.assertTrue(all(not p.is_alive() for p in processes), 'receiver timeout')
                    self.assertEqual([p.exitcode for p in processes], [0, 0])
                    received = [results.get(timeout=2) for _ in processes]
                    self.assertEqual([r['error'] for r in received], [None, None], received)
                    acks = [r['ack'] for r in received if r['ack'] is not None]
                    expected = envelopes[:1] if scenario == 'one_corrupt' else envelopes
                    self.assertCountEqual(acks, expected)
                finally:
                    for process in processes:
                        if process.pid is not None:
                            if process.is_alive():
                                process.terminate()
                                process.join(5)
                            process.close()
                    results.close()
                    results.join_thread()
                count = 2 if scenario == 'distinct' else 1
                with closing(sqlite3.connect(db)) as con:
                    self.assertEqual(con.execute('SELECT payload FROM inbox').fetchall(), [(payload,)] * count)
                    self.assertEqual(con.execute('SELECT payload FROM effects').fetchall(), [(payload,)] * count)
                    identities = [json.loads(row[0]) for row in con.execute('SELECT identity FROM inbox')]
                    self.assertCountEqual(identities, envelopes if scenario == 'distinct' else envelopes[:1])

    def test_conflicting_stored_payload_is_not_acknowledged_or_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'receiver.sqlite'
            envelope, payload = self.doc['envelope'], self.doc['payload'].encode('utf-8')
            self.assertEqual(D.receive(db, envelope, payload, envelope, dedup=True), envelope)
            with closing(sqlite3.connect(db)) as con, con:
                con.execute('UPDATE inbox SET payload=?', (b'conflicting bytes',))
            self.assertIsNone(D.receive(db, envelope, payload, envelope, dedup=True))
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT payload FROM inbox').fetchall(), [(b'conflicting bytes',)])
                self.assertEqual(con.execute('SELECT payload FROM effects').fetchall(), [(payload,)])

    def test_case_names_do_not_control_filesystem_paths(self):
        case = dict(self.doc['cases'][0], id='../../outside')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'evidence'
            D.run_benchmark(dict(self.doc, cases=[case]), root)
            self.assertEqual(sorted(p.name for p in root.iterdir()), sorted(f'0-{p}.sqlite' for p in D.POLICIES))
            with self.assertRaisesRegex(ValueError, 'refuse to reuse'):
                D.run_benchmark(dict(self.doc, cases=[case]), root)

    def test_malformed_fixtures_fail_before_effects(self):
        mutations = [lambda d: d.update(schema_version=True), lambda d: d.update(attempt_limit=True),
                     lambda d: d.update(cases=[]), lambda d: d.update(payload='wrong bytes'),
                     lambda d: d['envelope'].update(epoch=True), lambda d: d['envelope'].pop('sender'),
                     lambda d: d['cases'].append(copy.deepcopy(d['cases'][0])),
                     lambda d: d['cases'][0].update(faults=['unknown']),
                     lambda d: d['cases'][0]['expected'].update(effect_count=True),
                     lambda d: d['cases'][0]['expected_attempts'].update(ack_retry=True)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = copy.deepcopy(self.doc)
                mutate(document)
                with self.assertRaises(ValueError):
                    D.run_benchmark(document)

    def test_wrong_answers_and_bad_input_have_distinct_cli_status(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.json'
            wrong = copy.deepcopy(self.doc)
            wrong['cases'][0]['expected']['effect_count'] = 0
            for document, code in [(wrong, 1), (dict(self.doc, schema_version=2), 2), (None, 2)]:
                path.write_text(json.dumps(document), encoding='utf-8')
                run = subprocess.run([sys.executable, D.__file__, '--cases', str(path)],
                                     capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(run.returncode, code, run.stdout + run.stderr)
                self.assertEqual(run.stderr, '')
                self.assertIsInstance(json.loads(run.stdout), dict)


if __name__ == '__main__':
    unittest.main()
