#!/usr/bin/env python3
"""Select evidence for root-reviewed requirements from one pinned JSON register.

OBSERVED means all declared requirements have known, nonconflicting values. It
does not mean approval or semantic completeness. Offline, stable snapshots only.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

if __name__ == '__main__':
    # Read-only CLI, including when Python -E ignores environment settings.
    sys.dont_write_bytecode = True
import read_evidence as E


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
        raise ValueError('IDs must be 1 to 128 simple ASCII characters')


def fields(value, expected):
    if type(value) is not dict or set(value) != expected:
        raise ValueError('fields do not match schema')


def version(document):
    if type(document['schema_version']) is not int or document['schema_version'] != 1:
        raise ValueError('unsupported schema version')


def validate_question(question):
    fields(question, {'schema_version', 'question_id', 'question', 'subject', 'source_sha256',
                      'max_source_bytes', 'max_result_bytes', 'requirements'})
    version(question)
    identifier(question['question_id']); identifier(question['subject'])
    text = question['question']
    if type(text) is not str or not text.strip() or len(text) > 4096:
        raise ValueError('question must contain 1 to 4096 characters')
    E.pin(question['source_sha256'])
    for name in ('max_source_bytes', 'max_result_bytes'):
        if type(question[name]) is not int or not 1 <= question[name] <= E.DOCUMENT_LIMIT:
            raise ValueError(name + ' must be an integer from 1 to 4194304')
    rows = question['requirements']
    if type(rows) is not list or not 1 <= len(rows) <= 32:
        raise ValueError('expected 1 to 32 requirements')
    ids, purposes = set(), set()
    for row in rows:
        fields(row, {'id', 'purpose'})
        identifier(row['id'])
        if row['id'] in ids:
            raise ValueError('requirement IDs must be unique')
        if type(row['purpose']) is not str or row['purpose'] not in ('answer', 'guard'):
            raise ValueError('requirement purpose must be answer or guard')
        ids.add(row['id']); purposes.add(row['purpose'])
    if purposes != {'answer', 'guard'}:
        raise ValueError('question needs both answer and guard requirements')


def validate_source(document):
    fields(document, {'schema_version', 'observations'})
    version(document)
    rows = document['observations']
    if type(rows) is not list:
        raise ValueError('observations must be an array')
    ids = set()
    for row in rows:
        fields(row, {'id', 'subject', 'requirement', 'state', 'value', 'qualifiers'})
        for name in ('id', 'subject', 'requirement'):
            identifier(row[name])
        if row['id'] in ids:
            raise ValueError('observation IDs must be unique')
        ids.add(row['id'])
        if type(row['state']) is not str or row['state'] not in ('known', 'unknown'):
            raise ValueError('observation state must be known or unknown')
        if row['state'] == 'unknown' and row['value'] is not None:
            raise ValueError('unknown observations must have a null value')
        if type(row['qualifiers']) is not list or any(type(x) is not str for x in row['qualifiers']):
            raise ValueError('qualifiers must be an array of strings')


def read_requirements(question_path, expected_question_sha256, source_path):
    metrics = dict(question_reads=0, question_bytes_read=0, source_reads=0, source_bytes_read=0)
    try:
        E.pin(expected_question_sha256)
        raw = E.read_regular(question_path, E.REQUEST_LIMIT, metrics, 'question')
        if E.digest(raw) != expected_question_sha256:
            raise ValueError('question differs from the caller pin')
        question = E.load_json(raw)
        validate_question(question)
        source = E.read_regular(source_path, question['max_source_bytes'], metrics, 'source')
        if E.digest(source) != question['source_sha256']:
            raise ValueError('source differs from the approved question pin')
        document = E.load_json(source)
        validate_source(document)
        # Include every exact match, preserving source order and all qualifiers.
        # Never substitute another subject or prefer a newer/successful record.
        selected, gaps = [], []
        for requirement in question['requirements']:
            matches = [row for row in document['observations']
                       if row['subject'] == question['subject'] and row['requirement'] == requirement['id']]
            reason = None
            if not matches:
                reason = 'MISSING'
            elif any(row['state'] == 'unknown' or row['value'] is None for row in matches):
                reason = 'UNKNOWN'
            elif len({E.encode(row['value']) for row in matches}) != 1:
                reason = 'CONFLICT'
            if reason:
                gaps.append(dict(id=requirement['id'], reason=reason))
            else:
                selected.append(dict(requirement, observations=matches))
        result = dict(schema_version=1, status='INSUFFICIENT' if gaps else 'OBSERVED',
                      scope='declared_requirements_only', question_id=question['question_id'],
                      subject=question['subject'], question_sha256=expected_question_sha256,
                      source_sha256=E.digest(source), metrics=metrics)
        if gaps:
            result['gaps'] = gaps
        else:
            result['requirements'] = selected
            if len(E.encode(result)) > question['max_result_bytes']:
                raise ValueError('result byte limit exceeded; never truncate required evidence')
        return result
    except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        # No partial observations are exposed on any failure.
        return dict(schema_version=1, status='REFUSED', error=str(exc), metrics=metrics)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question', type=Path, required=True)
    parser.add_argument('--sha256', required=True, help='independently approved question digest')
    parser.add_argument('--source', type=Path, required=True, help='explicit local register; no JSON paths are followed')
    args = parser.parse_args(argv)
    result = read_requirements(args.question, args.sha256, args.source)
    sys.stdout.write(E.encode(result).decode('utf-8'))
    return {'OBSERVED': 0, 'INSUFFICIENT': 1, 'REFUSED': 2}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
