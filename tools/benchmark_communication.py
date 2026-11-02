"""Offline communication comparison with separately authored delivery answers.

Run/contract/digest strings are labels, not authentication or artifact validation.
No native messages are sent and no acceptance or scheduling authority is granted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import benchmark_swarm as B

DEFAULT_CASES = Path(__file__).with_name('fixtures') / 'communication_benchmark.json'
POLICIES = ('dependency_epoch_dedup', 'run_scoped', 'run_contract_scoped')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _names(values):
    return (isinstance(values, list) and all(_text(v) for v in values)
            and len(values) == len(set(values)))


def validate(document):
    """Validate fixture structure without using a policy to manufacture answers."""
    _require(isinstance(document, dict) and type(document.get('schema_version')) is int
             and document['schema_version'] == 1, 'schema_version must be 1')
    cases = document.get('cases')
    _require(isinstance(cases, list) and bool(cases), 'cases must be a non-empty list')
    _require(all(isinstance(c, dict) for c in cases), 'cases must be objects')
    _require(_names([c.get('id') for c in cases]), 'case IDs must be unique strings')
    for c in cases:
        prefix = c['id'] + ': '
        _require(_text(c.get('description')) and _text(c.get('run_id')), prefix + 'description/run_id required')
        agents, epochs = c.get('agents'), c.get('current_epochs')
        _require(_names(agents) and bool(agents), prefix + 'agents must be unique strings')
        _require(isinstance(epochs, dict) and bool(epochs), prefix + 'current_epochs required')
        _require(all(s in agents and type(e) is int and e > 0 for s, e in epochs.items()),
                 prefix + 'epochs require known senders and positive integers')
        routes, contracts = c.get('recipients'), c.get('consumer_contracts')
        _require(isinstance(routes, dict) and set(routes) == set(epochs), prefix + 'routes must cover senders')
        _require(isinstance(contracts, dict), prefix + 'consumer_contracts must be an object')
        for recipient, by_sender in contracts.items():
            _require(recipient in agents and isinstance(by_sender, dict), prefix + 'invalid contract recipient')
            _require(all(s in epochs and _text(contract) for s, contract in by_sender.items()),
                     prefix + 'invalid sender/contract')
        for sender, recipients in routes.items():
            _require(_names(recipients) and all(r in agents and r != sender for r in recipients),
                     prefix + 'routes need unique known non-self recipients')
            _require(all(sender in contracts.get(r, {}) for r in recipients), prefix + 'route missing consumer contract')
        events = c.get('events')
        _require(isinstance(events, list) and all(isinstance(e, dict) for e in events), prefix + 'events must be objects')
        _require(_names([e.get('event_id') for e in events]), prefix + 'event IDs must be unique strings')
        for event in events:
            _require(_text(event.get('sender')) and event['sender'] in epochs, prefix + 'unknown event sender')
            _require(type(event.get('epoch')) is int and event['epoch'] > 0, prefix + 'invalid event epoch')
            _require(_text(event.get('artifact_digest')), prefix + 'artifact_digest required')
            # Missing scope is an intentional fault case, not an implicit default.
            _require(all(k not in event or _text(event[k]) for k in ('run_id', 'contract_id')),
                     prefix + 'scope fields must be non-empty strings when present')
        wanted = c.get('expected_deliveries')
        ids = {e['event_id']: e for e in events}
        _require(isinstance(wanted, list), prefix + 'expected_deliveries must be a list')
        _require(all(isinstance(pair, list) and len(pair) == 2 and all(_text(v) for v in pair)
                     and pair[0] in ids and pair[1] in routes[ids[pair[0]]['sender']] for pair in wanted),
                 prefix + 'expected deliveries must name existing event/route pairs')
        _require(len(wanted) == len({tuple(p) for p in wanted}), prefix + 'duplicate expected delivery')
        outcomes = c.get('expected_policy_correct')
        _require(isinstance(outcomes, dict) and set(outcomes) == set(POLICIES)
                 and all(type(v) is bool for v in outcomes.values()), prefix + 'policy expectations required')


def route(case, policy):
    if policy == 'dependency_epoch_dedup':
        return B.communication_trial(case)[policy]['deliveries']
    if policy == 'run_scoped':
        scoped = dict(case, events=[e for e in case['events'] if e.get('run_id') == case['run_id']])
        return B.communication_trial(scoped)['dependency_epoch_dedup']['deliveries']
    if policy != 'run_contract_scoped':
        raise ValueError('unknown policy: ' + str(policy))
    sent, seen = [], set()
    for event in case['events']:
        sender = event['sender']
        if event.get('run_id') != case['run_id'] or event['epoch'] != case['current_epochs'][sender]:
            continue
        for recipient in case['recipients'][sender]:
            contract = case['consumer_contracts'][recipient][sender]
            if event.get('contract_id') != contract:
                continue
            key = (case['run_id'], sender, event['epoch'], event['artifact_digest'], contract, recipient)
            if key not in seen:
                seen.add(key)
                sent.append([event['event_id'], recipient])
    return sent


def delivery_score(wanted, actual):
    expected_counts, counts = Counter(map(tuple, wanted)), Counter(map(tuple, actual))
    return dict(correct=actual == wanted, deliveries=actual, message_count=len(actual),
                unexpected_deliveries=[list(p) for p in (counts - expected_counts).elements()],
                missing_deliveries=[list(p) for p in (expected_counts - counts).elements()])


def run_benchmark(document):
    validate(document)
    results = []
    for case in document['cases']:
        outputs = {p: delivery_score(case['expected_deliveries'], route(case, p)) for p in POLICIES}
        results.append(dict(id=case['id'], expected_deliveries=case['expected_deliveries'], policies=outputs,
                            passed=all(outputs[p]['correct'] == case['expected_policy_correct'][p] for p in POLICIES)))
    metrics = {p: dict(correct_cases=sum(r['policies'][p]['correct'] for r in results),
                       message_count=sum(r['policies'][p]['message_count'] for r in results),
                       unexpected_deliveries=sum(len(r['policies'][p]['unexpected_deliveries']) for r in results),
                       missing_deliveries=sum(len(r['policies'][p]['missing_deliveries']) for r in results)) for p in POLICIES}
    comparisons = {}
    for policy in POLICIES[1:]:
        recoveries = [r['id'] for r in results if r['policies'][policy]['correct'] and not r['policies'][POLICIES[0]]['correct']]
        regressions = [r['id'] for r in results if not r['policies'][policy]['correct'] and r['policies'][POLICIES[0]]['correct']]
        comparisons[policy] = dict(recoveries=recoveries, regressions=regressions,
            passes_case_gate=bool(recoveries) and not regressions and metrics[policy]['correct_cases'] == len(results))
    return dict(schema_version=1, evidence='synthetic_known_answer', total=len(results),
                passed=sum(r['passed'] for r in results), cases=results, metrics=metrics, comparisons=comparisons,
                non_claims=['artifact authenticity', 'live transport or acknowledgement', 'LLM reasoning quality',
                            'speed, token or monetary savings', 'native dispatch or acceptance authority'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(json.loads(args.cases.read_text(encoding='utf-8')))
        status = int(report['passed'] != report['total'] or not report['comparisons']['run_contract_scoped']['passes_case_gate'])
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        report, status = dict(schema_version=1, error=str(exc)), 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
