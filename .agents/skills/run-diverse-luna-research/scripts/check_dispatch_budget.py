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
DYNAMIC_CODE_NAMES = {'eval', 'Function', 'AsyncFunction', 'GeneratorFunction',
                      'AsyncGeneratorFunction', 'constructor', 'globalThis', 'Reflect',
                      'getOwnPropertyDescriptor', 'getOwnPropertyDescriptors', 'getPrototypeOf'}
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
                elif quote == '`' and source.startswith('${', index):
                    raise ValueError('cannot count dispatch inside template interpolation')
                elif source[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            else:
                raise ValueError('cannot count dispatch in an unterminated string')
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
        if literal_key and literal_key.group(2) not in DYNAMIC_CODE_NAMES:
            continue
        raise ValueError('cannot count dispatch through a dynamic executable property')
    return visible


def _reject_destructuring(visible: str) -> None:
    """Reject binding patterns, whose literal property names are masked.

    Match delimiters before inspecting assignment/iteration targets and formal
    parameters. This rejects the syntax class, not a list of dangerous keys;
    ordinary object arguments and numeric/literal data accesses remain usable.
    """
    stack = []
    pairs = {}
    for index, character in enumerate(visible):
        if character in '([{':
            stack.append((character, index))
        elif character in ')]}':
            if not stack or stack[-1][0] != {')': '(', ']': '[', '}': '{'}[character]:
                raise ValueError('cannot count dispatch in an unbalanced wrapper')
            _, start = stack.pop()
            pairs[start] = index
    if stack:
        raise ValueError('cannot count dispatch in an unbalanced wrapper')
    binding_suffix = re.compile(r'\s*(?:=(?!=|>)|(?:in|of)\b)')
    parameter_suffix = re.compile(r'\s*(?:\{|=>)')
    for start, stop in pairs.items():
        if visible[start] in '[{':
            if binding_suffix.match(visible, stop + 1):
                raise ValueError('cannot count dispatch through destructuring')
        elif parameter_suffix.match(visible, stop + 1):
            # A function/method/catch/arrow parameter list can extract a hidden
            # executable property too. Inspect only parameter starts, skipping
            # complete nested expressions so object-valued defaults stay valid.
            index = start + 1
            parameter_start = True
            while index < stop:
                character = visible[index]
                if character.isspace():
                    index += 1
                    continue
                if parameter_start and visible.startswith('...', index):
                    index += 3
                    continue
                if parameter_start and character in '[{':
                    raise ValueError('cannot count dispatch through destructuring')
                if character == ',':
                    parameter_start = True
                else:
                    parameter_start = False
                index = pairs.get(index, index) + 1


def wrapped_dispatch_calls(source: str) -> list[tuple[str, int]]:
    """Return dispatch names and opening-parenthesis ends for literal calls.

    Tool aliases/computed access cannot establish invocation counts. Reject
    them rather than allowing a zero count to authorize further delegation.
    """
    visible = _visible_wrapper_code(source)
    _reject_destructuring(visible)
    # Dynamic code can invoke a native tool without a visible literal call site.
    # Reject it even when the eventual dispatch count would otherwise be zero.
    if re.search(r'\b(?:' + '|'.join(sorted(DYNAMIC_CODE_NAMES)) + r'|import)\b|\\', visible):
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
    if calls and re.search(r'\b(?:for|while|do|if|switch|function|class|get|set|try|catch|finally)\b|=>|\?|&&|\|\||\)\s*\{', visible):
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
    if not isinstance(first, dict) or first.get('type') != 'session_meta':
        raise ValueError(f'no session metadata: {path}')
    payload = first.get('payload')
    if not isinstance(payload, dict) or not isinstance(payload.get('id'), str) or not payload['id'].strip():
        raise ValueError(f'session metadata must contain an object with a non-empty id: {path}')
    return payload


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
    if not isinstance(value, str):
        raise ValueError('timestamps must be ISO-8601 strings')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamps must have a timezone')
    return result


def validate_state(state):
    if not isinstance(state, dict):
        raise ValueError('state must be a JSON object')
    if type(state.get('version')) is not int or state['version'] != 1:
        raise ValueError('state.version must be 1')
    if not isinstance(state.get('root_thread_id'), str) or not state['root_thread_id'].strip():
        raise ValueError('state.root_thread_id must be a non-empty string')
    rollouts = state.get('rollouts')
    if not isinstance(rollouts, list) or not rollouts or any(
        not isinstance(path, str) or not path.strip() for path in rollouts
    ):
        raise ValueError('state.rollouts must be a non-empty array of paths')
    for field in ('attempt_budget_N', 'concurrency_cap_C', 'greatest_observed_attempts'):
        value = state.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(f'state.{field} must be a non-negative integer')
    parse_time(state.get('started_at'))


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
                if not isinstance(item, dict):
                    raise ValueError(f'rollout records must be JSON objects: {path}')
                p = item.get('payload', {})
                if item.get('type') != 'response_item':
                    continue
                if not isinstance(p, dict):
                    raise ValueError(f'response_item payload must be an object: {path}')
                if item.get('timestamp') and parse_time(item['timestamp']) < since:
                    continue
                names = dispatch_names(p)
                if not names:
                    continue
                if not item.get('timestamp'):
                    raise ValueError('dispatch call lacks timestamp')
                call_id = p.get('call_id')
                if not isinstance(call_id, str) or not call_id.strip():
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
    reason_code = 'INVALID_CONFIG'
    try:
        config = tomllib.loads(args.config.read_text(encoding='utf-8-sig'))
        agents = config.get('agents', {})
        if not isinstance(agents, dict):
            raise ValueError('configuration agents must be a TOML table')
        cap = agents.get('max_concurrent_threads_per_session')
        if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= MAX_CHILDREN:
            raise ValueError(f'loaded configuration must cap children at {MAX_CHILDREN} or fewer')
        if args.init:
            reason_code = 'INVALID_STATE'
            if args.state.exists():
                raise ValueError('state already exists; continuation must reuse it')
            if args.root_rollout is None:
                raise ValueError('--init requires --root-rollout')
            reason_code = 'INVALID_ROLLOUT'
            root_meta = meta(args.root_rollout)
            if parent(root_meta.get('source')) or root_meta.get('parent_thread_id'):
                raise ValueError('initialize the objective budget only at the real root')
            state = {'version': 1, 'root_thread_id': root_meta['id'],
                     'started_at': datetime.now(timezone.utc).isoformat(),
                     'attempt_budget_N': args.budget, 'concurrency_cap_C': cap,
                     'greatest_observed_attempts': 0,
                     'rollouts': [str(args.root_rollout.resolve())]}
        else:
            reason_code = 'INVALID_STATE'
            state = json.loads(args.state.read_text(encoding='utf-8'))
            validate_state(state)
            if cap != state['concurrency_cap_C']:
                raise ValueError('configured capacity changed during this objective')
        reason_code = 'INVALID_STATE'
        validate_state(state)
        reason_code = 'INVALID_ROLLOUT'
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
        reason_code = 'TRACE_VALIDATION_FAILED'
        counts = observed_attempts(state)
        reason_code = 'DISPATCH_LIMIT'
        check_limits(state, counts, args.new_spawns, args.new_followups,
                     args.open_children, args.verification)
        state['greatest_observed_attempts'] = counts['total']
        reason_code = 'STATE_WRITE_FAILED'
        args.state.parent.mkdir(parents=True, exist_ok=True)
        with args.state.open('x' if args.init else 'w', encoding='utf-8') as dest:
            json.dump(state, dest, ensure_ascii=False, indent=2)
        print(json.dumps({'schema_version': 1, 'status': 'PASS', 'observed': counts,
                          'attempt_budget_N': state['attempt_budget_N'],
                          'concurrency_cap_C': cap,
                          'planned': args.new_spawns + args.new_followups}))
        return 0
    except (ValueError, OSError, KeyError, StopIteration) as error:
        print(json.dumps({'schema_version': 1, 'status': 'BLOCK_NEW_DISPATCH',
                          'reason_code': reason_code, 'reason': str(error) or type(error).__name__}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
