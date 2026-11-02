#!/usr/bin/env python3
"""Read exact, approved JSON fields and their guards from one pinned source.

Offline, read-only, single-owner snapshots only. A verified partial view is not
approval, completeness, source authenticity or proof that guards are sufficient.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys

REQUEST_LIMIT = 16384
DOCUMENT_LIMIT = 4 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def load_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('non-finite JSON number')
        try:
            exact = Decimal(value) == Decimal(str(result))
        except InvalidOperation:
            exact = False
        if not exact:
            raise ValueError('JSON decimal would lose precision; retain exact values as strings')
        return result

    def constant(_):
        raise ValueError('non-JSON constant')

    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                      parse_float=number, parse_constant=constant)


def pin(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('expected an independently approved lowercase SHA256')


def tokens(pointer):
    if type(pointer) is not str or (pointer and not pointer.startswith('/')):
        raise ValueError('expected a JSON string pointer, not a URI fragment')
    if re.search(r'~(?![01])', pointer):
        raise ValueError('invalid JSON pointer escape')
    return [x.replace('~1', '/').replace('~0', '~') for x in pointer.split('/')[1:]]


def select(document, pointer):
    value = document
    for token in tokens(pointer):
        if type(value) is dict and token in value:
            value = value[token]
        elif type(value) is list and re.fullmatch(r'0|[1-9][0-9]*', token):
            index = int(token)
            if index >= len(value):
                raise ValueError('JSON pointer index is absent')
            value = value[index]
        else:
            raise ValueError('JSON pointer does not resolve')
    return value


def validate_request(request):
    fields = {'schema_version', 'source_sha256', 'max_source_bytes', 'max_result_bytes', 'selections'}
    if type(request) is not dict or set(request) != fields:
        raise ValueError('request fields do not match schema')
    if type(request['schema_version']) is not int or request['schema_version'] != 1:
        raise ValueError('unsupported request schema')
    pin(request['source_sha256'])
    for field in ('max_source_bytes', 'max_result_bytes'):
        if type(request[field]) is not int or not 1 <= request[field] <= DOCUMENT_LIMIT:
            raise ValueError(field + ' must be an integer from 1 to 4194304')
    rows = request['selections']
    if type(rows) is not list or not 1 <= len(rows) <= 32:
        raise ValueError('expected 1 to 32 selections')
    ids, pointers, purposes = set(), set(), set()
    for row in rows:
        if type(row) is not dict or set(row) != {'id', 'pointer', 'purpose'}:
            raise ValueError('selection fields do not match schema')
        name, purpose = row['id'], row['purpose']
        if type(name) is not str or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}', name) or name in ids:
            raise ValueError('selection IDs must be unique simple names')
        if type(purpose) is not str or purpose not in ('answer', 'guard'):
            raise ValueError('selection purpose must be answer or guard')
        tokens(row['pointer'])
        if row['pointer'] in pointers:
            raise ValueError('duplicate selection pointer')
        ids.add(name); pointers.add(row['pointer']); purposes.add(purpose)
    if purposes != {'answer', 'guard'}:
        raise ValueError('request needs both answer and guard selections')


def read_regular(path, limit, metrics, label):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('only ordinary files are supported')
    # Detect static unsafe leaf types before opening; concurrent swaps/ancestor
    # aliases are outside the stable, single-owner snapshot contract.
    with path.open('rb') as handle:
        metrics[label + '_reads'] += 1
        data = handle.read(limit + 1)
    metrics[label + '_bytes_read'] += len(data)
    if len(data) > limit:
        raise ValueError(label + ' byte limit exceeded')
    return data


def read_evidence(request_path, expected_request_sha256, source_path):
    metrics = dict(request_reads=0, request_bytes_read=0, source_reads=0, source_bytes_read=0)
    try:
        pin(expected_request_sha256)
        raw = read_regular(request_path, REQUEST_LIMIT, metrics, 'request')
        if digest(raw) != expected_request_sha256:
            raise ValueError('request differs from the caller pin')
        request = load_json(raw)
        validate_request(request)
        source = read_regular(source_path, request['max_source_bytes'], metrics, 'source')
        if digest(source) != request['source_sha256']:
            raise ValueError('source differs from the approved request pin')
        document = load_json(source)
        values = [dict(row, value=select(document, row['pointer'])) for row in request['selections']]
        result = dict(schema_version=1, status='VERIFIED', scope='selected_fields_only',
                      request_sha256=expected_request_sha256, source_sha256=digest(source),
                      values=values, metrics=metrics)
        if len(encode(result)) > request['max_result_bytes']:
            raise ValueError('result byte limit exceeded; narrow the reviewed query, never truncate')
        return result
    except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        # No values are exposed until every selection and the result limit pass.
        return dict(schema_version=1, status='REFUSED', error=str(exc), metrics=metrics)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--sha256', required=True, help='independently approved request digest')
    parser.add_argument('--source', type=Path, required=True, help='explicit local snapshot; no paths are followed from JSON')
    args = parser.parse_args(argv)
    result = read_evidence(args.request, args.sha256, args.source)
    sys.stdout.write(encode(result).decode('utf-8'))
    return 0 if result['status'] == 'VERIFIED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
