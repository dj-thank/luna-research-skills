#!/usr/bin/env python3
"""Preflight native dispatch against an objective-bound, monotonic attempt budget."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tomllib

MAX_CHILDREN = 6
MAX_ATTEMPTS = 12
MAX_WAVE = 3

DISPATCH_NAMES = {'spawn_agent', 'followup_task'}
TOOL_REFERENCE = re.compile(r'\btools(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*)+')


def is_exec_wrapper(payload: dict) -> bool:
    name = payload.get('name')
    return (payload.get('type') == 'custom_tool_call' and isinstance(name, str)
            and name.split('.')[-1].split('__')[-1] == 'exec')


def _visible_wrapper_code(source: str) -> str:
    """Mask literal/comment contents while preserving offsets into the receipt.

    This is a conservative lexer for literal exec wrappers, not a JS evaluator.
    Unsupported interpolation fails closed instead of hiding executable code.
    """
    code = list(source)
    index = 0
    regex_allowed = True
    previous_token = ''
    computed_accesses = []
    while index < len(source):
        start = index
        character = source[index]
        if source.startswith('//', index):
            end = source.find('\n', index)
            index = len(source) if end < 0 else end
        elif source.startswith('/*', index):
            end = source.find('*/', index + 2)
            if end < 0:
                raise ValueError('cannot count dispatch in an unterminated comment')
            index = end + 2
        elif character in '\"\'`':
            quote = character
            index += 1
            while index < len(source):
                if source[index] == '\\':
                    index += 2
                elif source[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            else:
                raise ValueError('cannot count dispatch in an unterminated string')
            if quote == '`' and '${' in source[start:index]:
                if re.search(r'\btools\b|(?:spawn_agent|followup_task)\b', source[start:index]):
                    raise ValueError('cannot count dispatch inside template interpolation')
            regex_allowed = False
            previous_token = 'literal'
        elif character == '/' and regex_allowed:
            index += 1
            in_class = False
            while index < len(source):
                if source[index] == '\\':
                    index += 2
                    continue
                if source[index] == '[':
                    in_class = True
                elif source[index] == ']':
                    in_class = False
                elif source[index] == '/' and not in_class:
                    index += 1
                    while index < len(source) and source[index].isalpha():
                        index += 1
                    break
                index += 1
            else:
                raise ValueError('cannot count dispatch in an unterminated regex')
            regex_allowed = False
            previous_token = 'literal'
        elif character == '/':
            raise ValueError('cannot count dispatch after an ambiguous slash; use direct native calls')
        elif character.isalpha() or character in '_$':
            index += 1
            while index < len(source) and (source[index].isalnum() or source[index] in '_$'):
                index += 1
            word = source[start:index]
            regex_allowed = previous_token != '.' and word in {'return', 'throw', 'case', 'await', 'yield', 'typeof', 'void', 'delete', 'new', 'else', 'do', 'in', 'instanceof', 'extends', 'break', 'continue', 'debugger'}
            previous_token = word
            continue
        elif source[index:index + 2] in {'++', '--'}:
            previous_token = source[index:index + 2]
            regex_allowed = False
            index += 2
            continue
        else:
            if not character.isspace():
                if character == '[' and not regex_allowed:
                    computed_accesses.append(index)
                previous_token = character
                regex_allowed = character not in ')]}.' and not character.isdigit()
            index += 1
            continue
        code[start:index] = ' ' * (index - start)
        # Preserve a literal's start for argument parsing, never its contents.
        if character in '\"\'`' or (character == '/' and not source.startswith(('//', '/*'), start)):
            code[start] = character
    visible = ''.join(code)
    for start in computed_accesses:
        stop = visible.find(']', start + 1)
        if stop < 0:
            raise ValueError('cannot count dispatch through an incomplete computed property')
        key = source[start + 1:stop].strip()
        literal_key = re.fullmatch(r"([\"'])([A-Za-z0-9_]+)\1", key)
        if key.isdecimal():
            continue
        if literal_key and literal_key.group(2) not in {'constructor', 'eval', 'Function', 'AsyncFunction', 'GeneratorFunction', 'AsyncGeneratorFunction'}:
            continue
        raise ValueError('cannot count dispatch through a dynamic executable property')
    return visible


def wrapped_dispatch_calls(source: str) -> list[tuple[str, int]]:
    """Return dispatch names and opening-parenthesis ends for literal calls.

    Tool aliases/computed access cannot establish invocation counts. Reject
    them rather than allowing a zero count to authorize further delegation.
    """
    visible = _visible_wrapper_code(source)
    # Dynamic code can invoke a native tool without a visible literal call site.
    # Reject it even when the eventual dispatch count would otherwise be zero.
    if re.search(r'\b(?:eval|Function|AsyncFunction|GeneratorFunction|AsyncGeneratorFunction|constructor|globalThis|Reflect)\b|\\', visible):
        raise ValueError('cannot count dispatch through dynamic code execution')
    calls = []
    spans = []
    for token in re.finditer(r'\btools\b', visible):
        reference = TOOL_REFERENCE.match(visible, token.start())
        if reference is None:
            raise ValueError('cannot count dispatch through computed or aliased tools')
        end = reference.end()
        while end < len(visible) and visible[end].isspace():
            end += 1
        if end >= len(visible) or visible[end] != '(':
            raise ValueError('cannot count dispatch through a tool alias or indirect reference')
        components = [part.split('__')[-1] for part in re.sub(r'\s+', '', reference.group()).split('.')[1:]]
        if any(part in DISPATCH_NAMES for part in components[:-1]):
            raise ValueError('cannot count dispatch through an indirect native reference')
        name = components[-1]
        spans.append(reference.span())
        if name in DISPATCH_NAMES:
            calls.append((name, end + 1))
    for token in re.finditer(r'\b[A-Za-z_][A-Za-z0-9_]*\b', visible):
        if token.group().split('__')[-1] in DISPATCH_NAMES:
            if not any(start <= token.start() < end for start, end in spans):
                raise ValueError('cannot count dispatch through an indirect native reference')
    if calls and re.search(r'\b(?:for|while|do|if|switch|function|eval)\b|=>|\?|&&|\|\|', visible):
        raise ValueError('cannot count dispatch in dynamic wrapper; use direct native calls')
    return calls


def dispatch_names(payload: dict) -> list[str]:
    """Recognize direct native calls and the supported exec wrapper subset."""
    if payload.get('type') == 'function_call':
        name = payload.get('name')
        if not isinstance(name, str):
            return []
        name = name.split('.')[-1].split('__')[-1]
        return [name] if name in DISPATCH_NAMES else []
    if not is_exec_wrapper(payload) or not isinstance(payload.get('input'), str):
        return []
    return [name for name, _ in wrapped_dispatch_calls(payload['input'])]



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
                if item.get('type') != 'response_item' or not isinstance(p, dict):
                    continue
                if item.get('timestamp') and parse_time(item['timestamp']) < since:
                    continue
                names = dispatch_names(p)
                if not names:
                    continue
                if not item.get('timestamp'):
                    raise ValueError('dispatch call lacks timestamp')
                call_id = p.get('call_id')
                if not call_id:
                    raise ValueError('dispatch call lacks call_id')
                key = (ident, call_id)
                if key in seen:
                    continue
                seen.add(key)
                for name in names:
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
