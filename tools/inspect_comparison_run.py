#!/usr/bin/env python3
"""Read a comparison run's retained artifacts against an independent evidence pin.

Offline and read-only: no scoring, publishing, repair, retry or cleanup. Inspect a
stable directory with one owner; this is not an atomic snapshot or authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True

import check_comparison as C

ARTIFACTS = ('evidence.json', 'evidence.sha256', 'report.json')


def _kind(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        return 'link_or_reparse'
    if stat.S_ISDIR(info.st_mode):
        return 'directory'
    if stat.S_ISREG(info.st_mode):
        return 'file'
    return 'special'


def inspect_run(run, expected_sha256):
    """Classify the known accepted/.pending layout, without modifying any path."""
    if type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('expected SHA-256 must be 64 lowercase hex characters from trusted review')
    root = Path(run)

    def result(state, reason, **details):
        return dict(schema_version=1, state=state, complete=state.startswith('COMPLETE_'),
                    published=state == 'COMPLETE_PUBLISHED', expected_sha256=expected_sha256,
                    reason=reason, passes_case_gate=None, **details)

    root_kind = _kind(root)
    if root_kind is None:
        return result('INCOMPLETE', 'RUN_ABSENT')
    if root_kind != 'directory':
        raise ValueError('run must be an ordinary directory, not a link, reparse point or file')
    locations = {name: _kind(root / name) for name in ('accepted', '.pending')}
    if any(kind not in (None, 'directory') for kind in locations.values()):
        return result('CONFLICT', 'INVALID_LOCATION_TYPE', locations=locations)
    present = [name for name, kind in locations.items() if kind is not None]
    if len(present) > 1:
        return result('CONFLICT', 'AMBIGUOUS_LOCATIONS', locations=present)
    if not present:
        return result('INCOMPLETE', 'NO_KNOWN_BUNDLE')
    location = present[0]
    folder = root / location
    kinds = {name: _kind(folder / name) for name in ARTIFACTS}
    if any(kind not in (None, 'file') for kind in kinds.values()):
        return result('CONFLICT', 'INVALID_ARTIFACT_TYPE', location=location, artifacts=kinds)
    missing = [name for name, kind in kinds.items() if kind is None]
    if missing:
        return result('INCOMPLETE', 'MISSING_ARTIFACTS', location=location, missing=missing)
    # Only these three files are read. Detected links/reparse points were refused
    # above; a hostile concurrent path swap remains outside the single-owner model.
    contents = {name: (folder / name).read_bytes() for name in ARTIFACTS}
    try:
        sidecar = contents['evidence.sha256'].decode('utf-8').strip()
        if sidecar != expected_sha256:
            return result('CONFLICT', 'SIDECAR_PIN_MISMATCH', location=location)
        report = C.load_json(contents['report.json'])
        # C.check's None means "no supplied report". Here a report is mandatory.
        if type(report) is not dict:
            raise ValueError('report must be an object, not null or another JSON type')
        checked = C.check(contents['evidence.json'], expected_sha256, report)
    except (ValueError, TypeError, RecursionError) as exc:
        return result('CONFLICT', 'INVALID_DOCUMENT', location=location, error=str(exc))
    if not checked['consistent']:
        return result('CONFLICT', 'INCONSISTENT_BUNDLE', location=location, errors=checked['errors'])
    state = 'COMPLETE_PUBLISHED' if location == 'accepted' else 'COMPLETE_STAGED'
    found = result(state, 'PIN_AND_REPORT_VERIFIED', location=location,
                   artifact_sha256={name: hashlib.sha256(data).hexdigest() for name, data in contents.items()})
    found['passes_case_gate'] = checked['summary']['passes_case_gate']
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True, help='reserved run directory containing accepted or .pending')
    parser.add_argument('--sha256', required=True, help='evidence digest approved independently of the directory contents')
    args = parser.parse_args(argv)
    try:
        report = inspect_run(args.run, args.sha256)
        code = 0 if report['complete'] else 1
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        report = dict(schema_version=1, state='ERROR', complete=False, published=False,
                      passes_case_gate=None, error=str(exc))
        code = 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
