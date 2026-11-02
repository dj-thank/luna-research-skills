#!/usr/bin/env python3
"""Run a pinned deterministic review pair and export complete comparison evidence.

Read-only: JSON goes to stdout. Failures produce an audit, never partial evidence.
Source fingerprints describe local files, not authenticated execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

# A script invocation owns its interpreter. Set this before sibling imports so
# the CLI is read-only even when Python -E ignores cache-suppression variables.
# Do not introduce a process-wide policy change for library imports here.
if __name__ == '__main__':
    sys.dont_write_bytecode = True

import benchmark_review as R
import check_comparison as C


class ExportRejected(ValueError):
    def __init__(self, message, audit):
        super().__init__(message)
        self.audit = audit


def _sources(fixture_sha256):
    return dict(fixture_sha256=fixture_sha256,
                review_sha256=hashlib.sha256(Path(R.__file__).read_bytes()).hexdigest(),
                validator_sha256=hashlib.sha256(Path(R.B.__file__).read_bytes()).hexdigest(),
                exporter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def export_evidence(raw, expected_sha256, candidate='unique_critique'):
    """Execute exactly the requested pair; no hidden third policy or calibration."""
    audit = []
    try:
        if type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
            raise ValueError('a separately pinned lowercase fixture SHA-256 is required')
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise ValueError('fixture differs from caller pin; no evaluation started')
        if candidate not in R.POLICIES[1:]:
            raise ValueError('candidate must be checked_minority or unique_critique')
        document = C.load_json(raw)
        R.validate_document(document)
        source = _sources(digest)
        evidence = dict(schema_version=2, evidence_kind='synthetic_known_answer',
                        work_unit='deterministic_oracle_call', source=source,
                        policies=dict(baseline=R.POLICIES[0], candidate=candidate),
                        per_case_budget=document['budget'], cases=[], work=[])
        labels = document['valid_labels']
        for index, case in enumerate(document['cases']):
            choices = {}
            for role, policy in evidence['policies'].items():
                attempts = []
                audit.append(dict(case_id=case['id'], policy=role, attempts=attempts))
                record = R.evaluate(document, case, policy, source['validator_sha256'], attempts=attempts)
                if (record['choice'] != case['expected'][policy]
                        or type(case['expected_calls'][policy]) is not int
                        or record['oracle_calls'] != case['expected_calls'][policy]
                        or len(attempts) != record['oracle_calls']
                        or sum(c['new_calls'] for c in record['checks']) != len(attempts)
                        or any(a['status'] != 'returned' or type(a['verdict']) is not bool for a in attempts)
                        or any(c['verdict'] is not None and c['verdict'] != labels[c['proposal']]
                               for c in record['checks'])):
                    raise ValueError(f'case {case["id"]}: frozen outcomes, labels or attempted calls disagree')
                choices[role] = record['choice']
                evidence['work'].extend(dict(id=f'{role}/{index}/{n}', policy=role,
                                             phase='evaluation', case_id=case['id']) for n in range(len(attempts)))
            evidence['cases'].append(dict(id=case['id'], choices=choices,
                valid_answers=sorted(k for k, v in labels.items() if v),
                available_answers=sorted(set(case['independent'] + [case['critique']]))))
        if source != _sources(digest):
            raise ValueError('source files changed during export')
        # Validate the consumer contract before a complete document can escape.
        C.summarize(evidence, '0' * 64)
        return evidence
    except Exception as exc:
        # Preserve diagnostics for unexpected scorer errors too; never substitute
        # a partial success. Process interrupts still propagate normally.
        raise ExportRejected(str(exc), audit) from exc


def failure_report(error):
    attempts = [a for row in error.audit for a in row['attempts']]
    return dict(error=str(error), complete=False, attempted_calls=len(attempts),
                failed_calls=sum(a['status'] == 'failed' for a in attempts), audit=error.audit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=R.DEFAULT_CASES)
    parser.add_argument('--sha256', required=True, help='fixture digest approved before execution')
    parser.add_argument('--candidate', choices=R.POLICIES[1:], default='unique_critique')
    args = parser.parse_args(argv)
    try:
        report = export_evidence(args.cases.read_bytes(), args.sha256, args.candidate)
        status = 0
    except ExportRejected as exc:
        report, status = failure_report(exc), 2
    except OSError as exc:
        report, status = failure_report(ExportRejected(str(exc), [])), 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
