#!/usr/bin/env python3
"""Check required GitHub check-run evidence against a trusted local policy.

Read-only and offline. This success-only rule is not GitHub merge authorization,
provider authentication or proof that a snapshot is fresh and unfiltered.
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __name__ == '__main__':
    # Script-local interpreter policy, before any sibling import (including -E).
    sys.dont_write_bytecode = True

from check_comparison import load_json


def _name(value, where):
    if type(value) is not str or not value.strip():
        raise ValueError(f'{where}: expected a nonempty string')


def _sha(value, where):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError(f'{where}: expected a full lowercase 40-character commit SHA')


def _positive(value, where):
    if type(value) is not int or value < 1:
        raise ValueError(f'{where}: expected a positive integer')


def evaluate(policy, snapshot):
    if type(policy) is not dict or set(policy) != {'schema_version', 'expected_head', 'required_checks'}:
        raise ValueError('policy requires exactly schema_version, expected_head and required_checks')
    if type(policy['schema_version']) is not int or policy['schema_version'] != 1:
        raise ValueError('unsupported policy schema_version')
    head = policy['expected_head']
    _sha(head, 'expected_head')
    required = policy['required_checks']
    if type(required) is not list or not required:
        raise ValueError('required_checks must be a nonempty list from trusted requirements')
    keys = []
    for item in required:
        if type(item) is not dict or set(item) != {'name', 'app_id'}:
            raise ValueError('required check needs exactly name and app_id')
        _name(item['name'], 'required check name')
        _positive(item['app_id'], 'required app_id')
        key = (item['name'], item['app_id'])
        if key in keys:
            raise ValueError('duplicate required name/app pair')
        keys.append(key)
    if type(snapshot) is not dict or not {'total_count', 'check_runs'} <= set(snapshot):
        raise ValueError('snapshot must contain REST check-runs total_count and check_runs')
    total, rows = snapshot['total_count'], snapshot['check_runs']
    if type(total) is not int or total < 0 or type(rows) is not list:
        raise ValueError('total_count must be a nonnegative integer and check_runs a list')
    grouped, ids, blocking = defaultdict(list), set(), []
    if total != len(rows):
        blocking.append(dict(code='SNAPSHOT_COUNT_MISMATCH', declared=total, received=len(rows)))
    for row in rows:
        if type(row) is not dict or not {'id', 'name', 'head_sha', 'app', 'status', 'conclusion'} <= set(row):
            raise ValueError('check run is missing required REST fields')
        _positive(row['id'], 'check run id')
        if row['id'] in ids:
            raise ValueError('duplicate check run id')
        ids.add(row['id'])
        _name(row['name'], 'check run name')
        _sha(row['head_sha'], 'check run head_sha')
        _name(row['status'], 'check run status')
        if row['conclusion'] is not None:
            _name(row['conclusion'], 'check run conclusion')
        if type(row['app']) is not dict or 'id' not in row['app']:
            raise ValueError('check run needs a provider app id')
        _positive(row['app']['id'], 'check run app id')
        if row['head_sha'] != head:
            blocking.append(dict(code='HEAD_MISMATCH', check_id=row['id']))
        grouped[row['name'], row['app']['id']].append(row)
    passing, required_rows = 0, 0
    for name, app_id in keys:
        matches = grouped[name, app_id]
        required_rows += len(matches)
        identity = dict(name=name, app_id=app_id)
        if not matches:
            blocking.append(dict(code='MISSING_REQUIRED_CHECK', **identity))
        elif len(matches) != 1:
            blocking.append(dict(code='AMBIGUOUS_REQUIRED_CHECK', count=len(matches), **identity))
        else:
            row = matches[0]
            if row['status'] != 'completed':
                blocking.append(dict(code='REQUIRED_CHECK_NOT_COMPLETED', status=row['status'], **identity))
            elif row['conclusion'] != 'success':
                blocking.append(dict(code='REQUIRED_CHECK_NOT_SUCCESSFUL', conclusion=row['conclusion'], **identity))
            elif row['head_sha'] == head:
                passing += 1
    return dict(schema_version=1, expected_head=head, passes_required_checks=not blocking,
                required_total=len(keys), passing_required=passing,
                received_checks=len(rows), optional_checks=len(rows)-required_rows,
                blocking=blocking)


def check(policy_bytes, snapshot_bytes):
    result = evaluate(load_json(policy_bytes), load_json(snapshot_bytes))
    result.update(policy_sha256=hashlib.sha256(policy_bytes).hexdigest(),
                  snapshot_sha256=hashlib.sha256(snapshot_bytes).hexdigest())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = check(args.policy.read_bytes(), args.snapshot.read_bytes())
        status = 0 if report['passes_required_checks'] else 1
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        report, status = dict(passes_required_checks=False, error=str(exc)), 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
