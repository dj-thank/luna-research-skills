#!/usr/bin/env python3
"""Preflight native dispatch against an objective-bound, monotonic attempt budget."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tomllib

MAX_CHILDREN = 6
MAX_ATTEMPTS = 12
MAX_WAVE = 3


def meta(path: Path) -> dict:
    with path.open(encoding='utf-8') as source:
        first = json.loads(next(source))
    if first.get('type') != 'session_meta':
        raise ValueError(f'no session metadata: {path}')
    return first['payload']


def parent(value):
    if isinstance(value, dict):
        for key in ('parent_thread_id', 'parent_thread_uuid'):
            if value.get(key):
                return value[key]
        for item in value.values():
            found = parent(item)
            if found:
                return found
    return None


def parse_time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamps must have a timezone')
    return result


def observed_attempts(state: dict) -> dict:
    since = parse_time(state['started_at'])
    seen = set()
    counts = {'spawn_agent': 0, 'followup_task': 0}
    for location in state['rollouts']:
        path = Path(location)
        ident = meta(path).get('id')
        with path.open(encoding='utf-8') as source:
            for raw in source:
                item = json.loads(raw)
                p = item.get('payload', {})
                if item.get('type') != 'response_item' or p.get('type') != 'function_call':
                    continue
                name = p.get('name', '').split('.')[-1].split('__')[-1]
                if name not in counts:
                    continue
                if not item.get('timestamp'):
                    raise ValueError('dispatch call lacks timestamp')
                if parse_time(item['timestamp']) < since:
                    continue
                call_id = p.get('call_id')
                if not call_id:
                    raise ValueError('dispatch call lacks call_id')
                key = (ident, call_id)
                if key in seen:
                    continue
                seen.add(key)
                counts[name] += 1
    return {**counts, 'total': sum(counts.values())}


def check_limits(state, counts, new_spawns=0, new_followups=0,
                 open_children=0, verification=False):
    budget = state['attempt_budget_N']
    cap = state['concurrency_cap_C']
    wave = new_spawns + new_followups
    if any(not isinstance(x, int) or isinstance(x, bool) or x < 0
           for x in (budget, cap, new_spawns, new_followups, open_children)):
        raise ValueError('budget and dispatch counts must be non-negative integers')
    if not 4 <= budget <= MAX_ATTEMPTS:
        raise ValueError(f'attempt budget must be 4..{MAX_ATTEMPTS}')
    if not 1 <= cap <= MAX_CHILDREN:
        raise ValueError(f'child capacity must be 1..{MAX_CHILDREN}')
    if wave > MAX_WAVE:
        raise ValueError(f'one wave may start at most {MAX_WAVE} attempts')
    if wave > cap:
        raise ValueError('planned wave exceeds declared child capacity')
    if open_children + new_spawns > cap:
        raise ValueError('planned spawns exceed open-child capacity')
    if counts['total'] < state.get('greatest_observed_attempts', 0):
        raise ValueError('observed attempt count decreased; retain the original traces')
    reserve = max(1, (15 * budget + 99) // 100)
    limit = budget if verification else budget - reserve
    if counts['total'] + wave > limit:
        raise ValueError(f'used={counts["total"]}, planned={wave}, limit={limit}; '
                         'continue required work at the parent without new dispatch')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--config', type=Path, default=Path.home()/'.codex/config.toml')
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--root-rollout', type=Path)
    parser.add_argument('--budget', type=int, default=6)
    parser.add_argument('--add-rollout', action='append', default=[], type=Path)
    parser.add_argument('--new-spawns', type=int, default=0)
    parser.add_argument('--new-followups', type=int, default=0)
    parser.add_argument('--open-children', type=int, default=0)
    parser.add_argument('--verification', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = tomllib.loads(args.config.read_text(encoding='utf-8-sig'))
        cap = config.get('agents', {}).get('max_concurrent_threads_per_session')
        if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= MAX_CHILDREN:
            raise ValueError(f'loaded configuration must cap children at {MAX_CHILDREN} or fewer')
        if args.init:
            if args.state.exists():
                raise ValueError('state already exists; continuation must reuse it')
            if args.root_rollout is None:
                raise ValueError('--init requires --root-rollout')
            root_meta = meta(args.root_rollout)
            if parent(root_meta.get('source')) or root_meta.get('parent_thread_id'):
                raise ValueError('initialize the objective budget only at the real root')
            state = {'version': 1, 'root_thread_id': root_meta['id'],
                     'started_at': datetime.now(timezone.utc).isoformat(),
                     'attempt_budget_N': args.budget, 'concurrency_cap_C': cap,
                     'greatest_observed_attempts': 0,
                     'rollouts': [str(args.root_rollout.resolve())]}
        else:
            state = json.loads(args.state.read_text(encoding='utf-8'))
            if cap != state['concurrency_cap_C']:
                raise ValueError('configured capacity changed during this objective')
        if meta(Path(state['rollouts'][0])).get('id') != state['root_thread_id']:
            raise ValueError('state no longer binds to its original root')
        known = {meta(Path(path)).get('id') for path in state['rollouts']}
        for path in args.add_rollout:
            child = meta(path)
            owner = child.get('parent_thread_id') or parent(child.get('source'))
            if owner not in known:
                raise ValueError('added rollout is not a child of the registered tree')
            known.add(child['id'])
            resolved = str(path.resolve())
            if resolved not in state['rollouts']:
                state['rollouts'].append(resolved)
        counts = observed_attempts(state)
        check_limits(state, counts, args.new_spawns, args.new_followups,
                     args.open_children, args.verification)
        state['greatest_observed_attempts'] = counts['total']
        args.state.parent.mkdir(parents=True, exist_ok=True)
        with args.state.open('x' if args.init else 'w', encoding='utf-8') as dest:
            json.dump(state, dest, ensure_ascii=False, indent=2)
        print(json.dumps({'status': 'PASS', 'observed': counts,
                          'attempt_budget_N': state['attempt_budget_N'],
                          'concurrency_cap_C': cap,
                          'planned': args.new_spawns + args.new_followups}))
        return 0
    except (ValueError, OSError, KeyError, StopIteration) as error:
        print(json.dumps({'status': 'BLOCK_NEW_DISPATCH', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
