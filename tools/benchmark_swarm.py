"""Known-answer planning benchmark and synthetic communication ablation.

Expectations are authored in a separate fixture, never computed by the planner.
This measures orchestration decisions, not LLM reasoning, tokens or wall time.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / 'tools/fixtures/swarm_benchmark.json'
DEFAULT_PLANNER = ROOT / '.agents/skills/run-diverse-luna-project/scripts/plan_swarm.py'
sys.dont_write_bytecode = True


def materialize(document, case):
    ledger = copy.deepcopy(document['base_ledger'])
    ledger.update(copy.deepcopy(case.get('ledger_overrides', {})))
    rows = {row['attempt_id']: row for row in ledger['assignments']}
    for aid, changes in case.get('row_overrides', {}).items():
        if aid not in rows:
            raise ValueError(f'unknown fixture attempt: {aid}')
        rows[aid].update(copy.deepcopy(changes))
    return ledger


def score(expected, actual):
    selected = actual.get('selected_attempt_ids', [])
    reasons = {row['attempt_id']: {r['code'] for r in row['reasons']}
               for row in actual.get('blocked', [])}
    errors = {item['code'] for item in actual.get('errors', [])}
    wanted_errors = set(expected.get('errors', []))
    exact_selection = selected == expected['selected_attempt_ids']
    reason_match = all(set(codes) <= reasons.get(aid, set())
                       for aid, codes in expected.get('blocked_reasons', {}).items())
    return dict(passed=exact_selection and reason_match and errors == wanted_errors,
                selection_correct=exact_selection,
                unexpected_starts=sorted(set(selected) - set(expected['selected_attempt_ids'])),
                missed_ready=sorted(set(expected['selected_attempt_ids']) - set(selected)),
                blocker_reasons_correct=reason_match, error_codes_correct=errors == wanted_errors)


def communication_trial(case):
    """Route a labelled event stream; correctness comes from expected deliveries."""
    agents = case['agents']
    if len(set(agents)) != len(agents):
        raise ValueError('communication agents must be unique')
    deliveries = {}
    for policy in ('broadcast', 'dependency_only', 'dependency_epoch_dedup'):
        sent, seen = [], set()
        for event in case['events']:
            if policy == 'dependency_epoch_dedup':
                key = (event['sender'], event['epoch'], event['artifact_digest'])
                if event['epoch'] != case['current_epochs'][event['sender']] or key in seen:
                    continue
                seen.add(key)
            recipients = ([a for a in agents if a != event['sender']] if policy == 'broadcast'
                          else case['recipients'][event['sender']])
            sent.extend([event['event_id'], recipient] for recipient in recipients)
        wanted = case['expected_deliveries']
        deliveries[policy] = dict(deliveries=sent, message_count=len(sent),
                                  exact_expected_deliveries=sent == wanted)
    return deliveries


def run_benchmark(document, planner):
    cases = document.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('benchmark needs non-empty predeclared cases')
    names = [case['id'] for case in cases]
    if len(set(names)) != len(names):
        raise ValueError('case IDs must be unique')
    results = []
    for case in cases:
        ledger = materialize(document, case)
        try:
            actual = planner.plan(ledger, case.get('open_children', 0),
                                  planner.timestamp(case.get('now', document['now'])),
                                  specialist_model=case.get('specialist_model', 'gpt-6-luna'))
        except ValueError as exc:
            actual = {'errors': [{'code': 'INVALID_INPUT', 'message': str(exc)}]}
        result = dict(id=case['id'], description=case['description'], expected=case['expected'],
                      actual=actual, **score(case['expected'], actual))
        # Controlled ablations: same snapshot and oracle, one decision rule removed.
        barrier = copy.deepcopy(actual)
        if actual.get('active_attempt_ids'):
            barrier['selected_attempt_ids'] = []
        naive = {'selected_attempt_ids': [r['attempt_id'] for r in ledger['assignments']
                                         if r['execution_status'] == 'planned']}
        result['ablations'] = {name: score(case['expected'], output)
                               for name, output in [('wave_barrier', barrier), ('all_planned', naive)]}
        results.append(result)
    communications = communication_trial(document['communication'])
    return dict(schema_version=1, evidence='synthetic_known_answer',
                non_claims=['LLM reasoning quality', 'live speedup', 'token or monetary savings'],
                total=len(results), passed=sum(r['passed'] for r in results), cases=results,
                ablation_selection_correct={name: sum(r['ablations'][name]['selection_correct'] for r in results)
                                            for name in ('wave_barrier', 'all_planned')},
                communication=communications)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    parser.add_argument('--planner', type=Path, default=DEFAULT_PLANNER)
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.cases.read_text(encoding='utf-8'))
        spec = importlib.util.spec_from_file_location('benchmark_planner', args.planner)
        planner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(planner)
        report = run_benchmark(document, planner)
        status = int(report['passed'] != report['total'] or
                     not report['communication']['dependency_epoch_dedup']['exact_expected_deliveries'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        report, status = {'schema_version': 1, 'error': str(exc)}, 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
