"""Compare bounded review policies on independently labelled synthetic answers.

This is an offline experiment, not a dispatcher or a cache for LLM judgments.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import benchmark_swarm as B

DEFAULT_CASES = B.ROOT / 'tools/fixtures/review_benchmark.json'
POLICIES = ('checked_critique', 'checked_minority', 'unique_critique')


class OracleBudget:
    """Serial, in-memory experiment budget for the deterministic score function."""

    def __init__(self, limit, *, attempts=None):
        if type(limit) is not int or limit < 1:
            raise ValueError('oracle budget must be a positive integer')
        self.limit, self.calls, self.hits = limit, 0, 0
        self._cache = {}
        if attempts is not None and type(attempts) is not list:
            raise ValueError('attempts must be a list or None')
        self.attempts = attempts

    def check(self, expected, proposal, *, revision, epoch, reuse=False):
        # Full content is the key: IDs/digests supplied by an agent are not proof.
        key = json.dumps([revision, epoch, expected, proposal], sort_keys=True, allow_nan=False)
        if reuse and key in self._cache:
            self.hits += 1
            return self._cache[key]
        if self.calls >= self.limit:
            return None  # Unchecked, distinct from a rejected False verdict.
        self.calls += 1  # Failed attempts also consume the finite budget.
        event = {'status': 'started'}
        if self.attempts is not None:
            self.attempts.append(event)
        try:
            verdict = B.score(expected, proposal)['passed']
        except Exception:
            event['status'] = 'failed'
            raise
        event.update(status='returned', verdict=verdict)
        if reuse:
            self._cache[key] = verdict
        return verdict


def evaluate(document, case, policy, revision, *, attempts=None):
    if policy not in POLICIES:
        raise ValueError(f'unknown review policy: {policy}')
    ballots = case['independent']
    if not isinstance(ballots, list) or len(ballots) != 3:
        raise ValueError('each case requires three independent proposals')
    ranking = Counter(ballots).most_common()
    if ranking[0][1] < 2:
        raise ValueError('a strict majority is required; ties need a separate experiment')
    majority, critic = ranking[0][0], case['critique']
    minority = next((p for p in ballots if p != majority), critic)
    budget = OracleBudget(document['budget'], attempts=attempts)
    checks = []

    def check(pid):
        before = budget.calls
        value = budget.check(document['oracle'], document['proposals'][pid], revision=revision,
                             epoch=document['epoch'], reuse=policy == 'unique_critique')
        checks.append(dict(proposal=pid, verdict=value, new_calls=budget.calls-before))
        return value

    base_ok = check(majority)
    alternative = minority if policy == 'checked_minority' else critic
    alternate_ok = check(alternative)
    choice = alternative if alternate_ok is True else majority if base_ok is True else None
    if policy == 'unique_critique' and choice is None and budget.calls < budget.limit:
        if check(minority) is True:
            choice = minority
    labels = document['valid_labels']  # Judge independently of score's verdicts.
    correct = choice is not None and labels[choice]
    available = any(labels[p] for p in [*ballots, critic])
    return dict(choice=choice, correct=correct, false_accept=choice is not None and not correct,
                abstain=choice is None, missed_available=choice is None and available,
                oracle_calls=budget.calls, cache_hits=budget.hits,
                delivered_proposals=len(ballots)+1, checks=checks)


def validate_document(document):
    cases = document.get('cases')
    if not isinstance(cases, list) or not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('non-empty cases with unique IDs are required')
    proposals, labels = document['proposals'], document['valid_labels']
    if set(proposals) != set(labels) or any(type(v) is not bool for v in labels.values()):
        raise ValueError('every proposal needs an independent boolean correctness label')
    if document['budget'] != 2 or type(document['budget']) is not int:
        raise ValueError('this comparison requires a two-call budget')


def run_benchmark(document):
    validate_document(document)
    cases, labels = document['cases'], document['valid_labels']
    revision = hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest()
    records = []
    for case in cases:
        policies = {p: evaluate(document, case, p, revision) for p in POLICIES}
        passed = all(r['choice'] == case['expected'][p]
                     and r['oracle_calls'] == case['expected_calls'][p]
                     and all(c['verdict'] is None or c['verdict'] == labels[c['proposal']]
                             for c in r['checks']) for p, r in policies.items())
        records.append(dict(id=case['id'], passed=passed, policies=policies))
    metrics = ('correct', 'false_accept', 'abstain', 'missed_available', 'oracle_calls',
               'cache_hits', 'delivered_proposals')
    totals = {p: {m: sum(c['policies'][p][m] for c in records) for m in metrics} for p in POLICIES}
    comparisons = {}
    for policy in POLICIES[1:]:
        recoveries = [c['id'] for c in records if not c['policies'][POLICIES[0]]['correct']
                      and c['policies'][policy]['correct']]
        regressions = [c['id'] for c in records if c['policies'][POLICIES[0]]['correct']
                       and not c['policies'][policy]['correct']]
        comparisons[policy] = dict(recoveries=recoveries, regressions=regressions,
            passes_case_gate=all(c['passed'] for c in records) and bool(recoveries)
            and not regressions and totals[policy]['false_accept'] == 0)
    return dict(schema_version=1, evidence='synthetic_known_answer', total=len(records),
                passed=sum(c['passed'] for c in records), validator_revision=revision,
                metrics=totals, comparisons=comparisons, cases=records,
                non_claims=['LLM reasoning quality', 'live speedup', 'token or monetary savings',
                            'production policy acceptance'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    try:
        raw = args.cases.read_bytes()
        report = run_benchmark(json.loads(raw.decode('utf-8')))
        report['fixture_sha256'] = hashlib.sha256(raw).hexdigest()
        status = int(report['passed'] != report['total'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        report, status = {'schema_version': 1, 'error': str(exc)}, 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
