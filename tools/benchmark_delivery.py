"""Bounded delivery/ACK fault comparison using isolated SQLite effect rows.

This is an offline experiment, not a transport or an exactly-once guarantee for
external effects. Each receipt and local effect share one SQLite transaction.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

DEFAULT_CASES = Path(__file__).with_name('fixtures') / 'delivery_benchmark.json'
POLICIES = ('send_once', 'ack_retry', 'ack_retry_dedup')
FIELDS = ('run_id', 'sender', 'epoch', 'contract_id', 'recipient', 'delivery_id', 'artifact_digest')
FAULTS = {'ok', 'drop_data', 'drop_ack', 'corrupt_data', 'rollback', 'reopen'} | {
    prefix + field for prefix in ('data_', 'ack_') for field in FIELDS
}


def validate(document):
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int or document['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    if type(document.get('attempt_limit')) is not int or document['attempt_limit'] != 2:
        raise ValueError('this comparison requires a two-attempt ceiling')
    envelope, payload = document.get('envelope'), document.get('payload')
    if not isinstance(envelope, dict) or set(envelope) != set(FIELDS) or not isinstance(payload, str):
        raise ValueError('complete envelope and text payload required')
    for key, value in envelope.items():
        if key == 'epoch':
            valid = type(value) is int and value > 0
        else:
            valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            raise ValueError('invalid envelope field: ' + key)
    if hashlib.sha256(payload.encode('utf-8')).hexdigest() != envelope['artifact_digest']:
        raise ValueError('trusted payload and digest must agree')
    cases = document.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('non-empty cases required')
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not case['id'].strip() or case['id'] in seen:
            raise ValueError('unique string case IDs required')
        seen.add(case['id'])
        faults = case.get('faults')
        if not isinstance(faults, list) or not faults or any(not isinstance(f, str) or f not in FAULTS for f in faults):
            raise ValueError('unknown or missing fault schedule')
        expected = case.get('expected')
        if not isinstance(expected, dict) or set(expected) != {'effect_count', 'confirmed'} or type(expected['effect_count']) is not int or expected['effect_count'] not in (0, 1) or type(expected['confirmed']) is not bool:
            raise ValueError('expected local effect count and confirmation required')
        outcomes, attempts = case.get('expected_policy_correct'), case.get('expected_attempts')
        if not isinstance(outcomes, dict) or set(outcomes) != set(POLICIES) or any(type(v) is not bool for v in outcomes.values()):
            raise ValueError('boolean policy expectations required')
        if not isinstance(attempts, dict) or set(attempts) != set(POLICIES) or any(type(v) is not int or not 1 <= v <= 2 for v in attempts.values()):
            raise ValueError('expected attempt counts must be 1 or 2')


def receive(database, envelope, payload, expected, *, dedup, rollback=False):
    """Return an ACK only after committing the local receipt/effect transaction."""
    if envelope != expected or hashlib.sha256(payload).hexdigest() != expected['artifact_digest']:
        return None
    key = json.dumps(envelope, sort_keys=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS inbox (identity TEXT PRIMARY KEY, payload BLOB NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS effects (payload BLOB NOT NULL)')
        try:
            with connection:
                prior = connection.execute('SELECT payload FROM inbox WHERE identity=?', (key,)).fetchone() if dedup else None
                if prior is not None:
                    if prior[0] != payload:
                        return None
                else:
                    if dedup:
                        connection.execute('INSERT INTO inbox VALUES (?,?)', (key, payload))
                    if rollback:
                        raise RuntimeError('injected rollback before effect')
                    connection.execute('INSERT INTO effects VALUES (?)', (payload,))
        except RuntimeError:
            return None
        return dict(envelope)
    finally:
        connection.close()


def run_case(document, case, policy, database):
    if policy not in POLICIES:
        raise ValueError('unknown policy')
    expected = document['envelope']
    limit = 1 if policy == 'send_once' else document['attempt_limit']
    confirmed, trace = False, []
    for number in range(limit):
        fault = case['faults'][number] if number < len(case['faults']) else 'ok'
        envelope, payload, ack = dict(expected), document['payload'].encode('utf-8'), None
        if fault.startswith('data_'):
            field = fault.removeprefix('data_')
            envelope[field] = expected[field] + 1 if field == 'epoch' else 'mismatched'
        if fault == 'corrupt_data':
            payload += b'corrupted'
        if fault != 'drop_data':
            ack = receive(database, envelope, payload, expected, dedup=policy == 'ack_retry_dedup', rollback=fault == 'rollback')
        # Every receive closes its connection. Reopen loses the committed ACK,
        # and the next attempt must use the persisted DB, not process memory.
        if fault in {'drop_ack', 'reopen'}:
            ack = None
        if ack is not None and fault.startswith('ack_'):
            field = fault.removeprefix('ack_')
            ack[field] = expected[field] + 1 if field == 'epoch' else 'mismatched'
        confirmed = ack == expected
        trace.append(dict(attempt=number + 1, fault=fault, confirmed=confirmed))
        if confirmed:
            break
    if database.exists():
        with closing(sqlite3.connect(database)) as connection:
            effects = [row[0] for row in connection.execute('SELECT payload FROM effects')]
            receipts = connection.execute('SELECT count(*) FROM inbox').fetchone()[0]
    else:
        effects, receipts = [], 0
    actual = dict(effect_count=len(effects), confirmed=confirmed)
    return dict(actual, attempts=len(trace), receipt_count=receipts, trace=trace,
                payloads_valid=all(hashlib.sha256(p).hexdigest() == expected['artifact_digest'] for p in effects),
                correct=actual == case['expected'], status='confirmed' if confirmed else 'unconfirmed')


def run_benchmark(document, evidence_dir=None):
    validate(document)
    if evidence_dir is None:
        with tempfile.TemporaryDirectory(prefix='luna-delivery-') as temp:
            return run_benchmark(document, Path(temp))
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, case in enumerate(document['cases']):
        outputs = {}
        for policy in POLICIES:
            database = evidence_dir / f'{index}-{policy}.sqlite'
            if database.exists():
                raise ValueError('refuse to reuse prior evidence database')
            outputs[policy] = run_case(document, case, policy, database)
        passed = all(r['correct'] == case['expected_policy_correct'][p] and r['attempts'] == case['expected_attempts'][p]
                     and r['payloads_valid'] for p, r in outputs.items())
        results.append(dict(id=case['id'], expected=case['expected'], policies=outputs, passed=passed))
    metrics = {p: {key: sum(r['policies'][p][key] for r in results)
                   for key in ('correct', 'attempts', 'effect_count', 'confirmed')} for p in POLICIES}
    recoveries = [r['id'] for r in results if r['policies']['ack_retry_dedup']['correct'] and not r['policies']['send_once']['correct']]
    regressions = [r['id'] for r in results if not r['policies']['ack_retry_dedup']['correct'] and r['policies']['send_once']['correct']]
    return dict(schema_version=1, evidence='local_sqlite_effects_simulated_delivery', total=len(results),
                passed=sum(r['passed'] for r in results), cases=results, metrics=metrics,
                candidate_gate=bool(recoveries) and not regressions and metrics['ack_retry_dedup']['correct'] == len(results),
                recoveries=recoveries, regressions=regressions,
                non_claims=['live transport', 'exactly-once external side effects', 'process/power-loss recovery',
                            'authentication', 'LLM reasoning, latency, token or monetary savings', 'native dispatch authority'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.cases.read_text(encoding='utf-8'))
        report = run_benchmark(document)
        status = int(report['passed'] != report['total'] or not report['candidate_gate'])
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        report, status = dict(schema_version=1, error=str(exc)), 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
