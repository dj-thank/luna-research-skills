#!/usr/bin/env python3
"""Summarize or check a pinned, synthetic known-answer comparison. Read-only.

The caller must independently review the labels and recorded work, and pin their
bytes before consuming a report. Hash equality is not execution authentication.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROLES = ('baseline', 'candidate')
UNITS = ('deterministic_oracle_call', 'simulated_judge_lookup')


def _object(value, keys, where):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f'{where}: expected exactly {", ".join(keys)}')


def _name(value, where):
    if type(value) is not str or not value.strip():
        raise ValueError(f'{where}: expected a nonempty string')


def _names(value, where):
    if type(value) is not list:
        raise ValueError(f'{where}: expected a list')
    for item in value:
        _name(item, where)
    if len(set(value)) != len(value):
        raise ValueError(f'{where}: duplicate names')


def load_json(data):
    """Reject duplicate keys and non-JSON constants instead of silently coercing."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f'invalid JSON constant: {value}')

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def summarize(document, evidence_sha256):
    """Compute outcomes from choices/labels, never from a scorer's passed flag."""
    if type(document) is not dict:
        raise ValueError('evidence must be an object')
    version = document.get('schema_version')
    if type(version) is not int or version not in (1, 2):
        raise ValueError('unsupported evidence schema_version')
    keys = ('schema_version', 'evidence_kind', 'work_unit', 'policies', 'per_case_budget', 'cases', 'work')
    _object(document, keys + (('source',) if version == 2 else ()), 'evidence')
    if version == 2:
        _object(document['source'], ('fixture_sha256', 'review_sha256', 'validator_sha256', 'exporter_sha256'), 'source')
        for value in document['source'].values():
            if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('source fingerprints must be lowercase SHA-256')
    if document['evidence_kind'] != 'synthetic_known_answer':
        raise ValueError('only synthetic_known_answer evidence is supported')
    if document['work_unit'] not in UNITS:
        raise ValueError('unsupported work_unit')
    _object(document['policies'], ROLES, 'policies')
    for role in ROLES:
        _name(document['policies'][role], f'policies.{role}')
    if document['policies']['baseline'] == document['policies']['candidate']:
        raise ValueError('policy names must differ')
    budget = document['per_case_budget']
    if type(budget) is not int or budget < 1:
        raise ValueError('per_case_budget must be a positive integer')
    cases = document['cases']
    if type(cases) is not list or not cases:
        raise ValueError('cases must be a nonempty list')
    case_ids = set()
    for case in cases:
        _object(case, ('id', 'valid_answers', 'available_answers', 'choices'), 'case')
        _name(case['id'], 'case.id')
        if case['id'] in case_ids:
            raise ValueError('duplicate case id')
        case_ids.add(case['id'])
        _names(case['valid_answers'], 'valid_answers')
        _names(case['available_answers'], 'available_answers')
        _object(case['choices'], ROLES, 'choices')
        for choice in case['choices'].values():
            if choice is not None and (type(choice) is not str or choice not in case['available_answers']):
                raise ValueError('choice must be an available answer or null')
    work = document['work']
    if type(work) is not list:
        raise ValueError('work must be a list of recorded call attempts')
    seen, calls, calibration = set(), Counter(), Counter()
    for event in work:
        _object(event, ('id', 'policy', 'phase', 'case_id'), 'work event')
        _name(event['id'], 'work.id')
        if event['id'] in seen:
            raise ValueError('duplicate work event id')
        seen.add(event['id'])
        role, phase, cid = event['policy'], event['phase'], event['case_id']
        if role not in ROLES:
            raise ValueError('unknown work policy')
        if phase == 'calibration' and cid is None:
            calibration[role] += 1
        elif phase == 'evaluation' and type(cid) is str and cid in case_ids:
            calls[role, cid] += 1
            if calls[role, cid] > budget:
                raise ValueError('recorded evaluation exceeds per_case_budget')
        else:
            raise ValueError('work phase/case_id mismatch')
    metrics = {role: dict(correct=0, false_accept=0, abstain=0, missed_available=0,
                         evaluation_calls=0, calibration_calls=calibration[role],
                         total_calls=0) for role in ROLES}
    recoveries, regressions = [], []
    for case in cases:
        correct = {}
        for role in ROLES:
            choice = case['choices'][role]
            correct[role] = choice is not None and choice in case['valid_answers']
            abstain = choice is None
            row = metrics[role]
            row['correct'] += int(correct[role])
            row['false_accept'] += int(not abstain and not correct[role])
            row['abstain'] += int(abstain)
            row['missed_available'] += int(abstain and bool(set(case['valid_answers']) & set(case['available_answers'])))
            row['evaluation_calls'] += calls[role, case['id']]
        if correct['candidate'] and not correct['baseline']:
            recoveries.append(case['id'])
        if correct['baseline'] and not correct['candidate']:
            regressions.append(case['id'])
    for row in metrics.values():
        row['total_calls'] = row['evaluation_calls'] + row['calibration_calls']
    result = dict(schema_version=version, evidence_sha256=evidence_sha256,
                evidence_kind=document['evidence_kind'], work_unit=document['work_unit'],
                policies=document['policies'], total_cases=len(cases), metrics=metrics,
                recoveries=sorted(recoveries), regressions=sorted(regressions),
                passes_case_gate=bool(recoveries) and not regressions and metrics['candidate']['false_accept'] == 0)
    if version == 2:
        result['source'] = dict(document['source'])
    return result


def _differences(expected, actual, path='report'):
    # Python's True == 1 and 1.0 == 1 must not admit mistyped report metrics.
    if type(expected) is not type(actual):
        return [f'{path}: type mismatch']
    if isinstance(expected, dict):
        errors = [f'{path}: missing or extra fields'] if set(expected) != set(actual) else []
        for key in sorted(set(expected) & set(actual)):
            errors.extend(_differences(expected[key], actual[key], f'{path}.{key}'))
        return errors
    return [] if expected == actual else [f'{path}: mismatch']


def check(evidence_bytes, expected_sha256, report=None):
    if type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('expected SHA-256 must be 64 lowercase hex characters')
    actual = hashlib.sha256(evidence_bytes).hexdigest()
    if actual != expected_sha256:
        return dict(consistent=False, errors=['evidence: SHA-256 differs from caller pin'], summary=None)
    summary = summarize(load_json(evidence_bytes), actual)
    errors = [] if report is None else _differences(summary, report)
    return dict(consistent=not errors, errors=errors, summary=summary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--sha256', required=True, help='digest pinned independently of the report')
    parser.add_argument('--report', type=Path, help='check a report; omit to print a derived summary')
    args = parser.parse_args(argv)
    try:
        report = load_json(args.report.read_bytes()) if args.report else None
        if args.report and report is None:
            raise ValueError('report must be an object, not null')
        result = check(args.evidence.read_bytes(), args.sha256, report)
        print(json.dumps(result if args.report or not result['consistent'] else result['summary'], indent=2, sort_keys=True))
        return 0 if result['consistent'] else 1
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps(dict(error=str(exc)), ensure_ascii=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
