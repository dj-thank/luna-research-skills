import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('guard', Path(__file__).with_name('check_dispatch_budget.py'))
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


class DispatchBudgetTests(unittest.TestCase):
    def state(self, **extra):
        return {'attempt_budget_N': 6, 'concurrency_cap_C': 6,
                'greatest_observed_attempts': 0, **extra}

    def test_normal_two_worker_wave_preserves_review(self):
        GUARD.check_limits(self.state(), {'total': 1}, new_spawns=2)

    def test_followups_consume_the_same_budget(self):
        with self.assertRaises(ValueError):
            GUARD.check_limits(self.state(), {'total': 5}, new_followups=1)

    def test_verifier_can_use_protected_reserve(self):
        GUARD.check_limits(self.state(), {'total': 5}, new_spawns=1, verification=True)

    def test_large_wave_and_open_children_are_rejected(self):
        for args in ({'new_spawns': 4}, {'new_spawns': 1, 'open_children': 6}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                GUARD.check_limits(self.state(), {'total': 0}, **args)

    def test_budget_cannot_expand_to_legacy_32(self):
        with self.assertRaises(ValueError):
            GUARD.check_limits(self.state(attempt_budget_N=32), {'total': 0})

    def test_followup_wave_must_fit_declared_capacity(self):
        with self.assertRaises(ValueError):
            GUARD.check_limits(self.state(concurrency_cap_C=1), {'total': 0},
                               new_followups=3, open_children=1)

    def test_count_cannot_reset_after_continuation(self):
        with self.assertRaises(ValueError):
            GUARD.check_limits(self.state(greatest_observed_attempts=4), {'total': 3})

    def test_trace_counts_failed_starts_and_followups_once(self):
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder)/'root.jsonl'
            rows = [{'type': 'session_meta', 'payload': {'id': 'root'}}]
            for ident, name in [('one','spawn_agent'), ('two','collaboration.followup_task'),
                                ('three','spawn_agent'), ('three','spawn_agent')]:
                rows.append({'timestamp': '2026-10-13T01:00:00Z',
                             'type': 'response_item', 'payload': {
                                 'type': 'function_call', 'name': name, 'call_id': ident}})
            trace.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
            result = GUARD.observed_attempts({'started_at': '2026-10-12T00:00:00Z', 'rollouts': [str(trace)]})
            self.assertEqual(result, {'spawn_agent': 2, 'followup_task': 1, 'total': 3})

    def test_existing_objective_cannot_be_reinitialized(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder)/'config.toml'
            config.write_text('[agents]\nmax_concurrent_threads_per_session=6\n', encoding='utf-8')
            state = Path(folder)/'state.json'
            state.write_text('{}', encoding='utf-8')
            self.assertEqual(GUARD.main(['--state',str(state),'--config',str(config),'--init']), 2)

    def wrapped_counts(self, source, **payload_overrides):
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder) / 'root.jsonl'
            call = {'timestamp': '2026-10-13T01:00:00Z', 'type': 'response_item',
                    'payload': {'type': 'custom_tool_call', 'name': 'functions.exec',
                                'call_id': 'wrapped', 'input': source, **payload_overrides}}
            rows = [{'type': 'session_meta', 'payload': {'id': 'root'}}, call, call]
            trace.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
            return GUARD.observed_attempts({
                'started_at': '2026-10-12T00:00:00Z', 'rollouts': [str(trace)]})

    def test_wrapped_calls_count_individually_and_duplicate_receipts_once(self):
        result = self.wrapped_counts('''
            const a = await tools.multi_agent_v1__spawn_agent({message: "first"});
            const b = await tools.collaboration.spawn_agent({message: "second"});
            await tools.multi_agent_v1__followup_task({target: "a", message: "fix"});
        ''')
        self.assertEqual(result, {'spawn_agent': 2, 'followup_task': 1, 'total': 3})
        with self.assertRaises(ValueError):
            GUARD.check_limits(self.state(), result, new_spawns=3)

    def test_quoted_task_content_and_comments_are_not_dispatches(self):
        result = self.wrapped_counts('''
            // await tools.collaboration.spawn_agent({});
            /* await tools.collaboration.followup_task({}); */
            const example = 'await tools.collaboration.spawn_agent({})';
            await tools.multi_agent_v1__spawn_agent({
                message: "Example: tools.collaboration.followup_task({})"
            });
        ''')
        self.assertEqual(result, {'spawn_agent': 1, 'followup_task': 0, 'total': 1})

    def test_wrapped_dispatch_requires_call_id(self):
        with self.assertRaisesRegex(ValueError, 'call_id'):
            self.wrapped_counts('await tools.collaboration.spawn_agent({});', call_id=None)

    def test_dynamic_wrappers_fail_closed(self):
        for source in (
            'for (let i=0; i<10; i++) { await tools.collaboration.spawn_agent({}); }',
            'items.map(async x => await tools.collaboration.followup_task({}));',
            'const text = `${await tools.multi_agent_v1__spawn_agent({})}`;',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'cannot count dispatch'):
                self.wrapped_counts(source)

    def test_unrelated_exec_is_not_a_dispatch(self):
        self.assertEqual(self.wrapped_counts('text(await tools.exec_command({cmd: "echo hi"}));')['total'], 0)

    def test_indirect_tool_references_fail_closed(self):
        for source in (
            'await tools["multi_agent_v1__spawn_agent"]({});',
            'const dispatch = tools.multi_agent_v1__spawn_agent; await dispatch({});',
            'const t = tools; await t.spawn_agent({});',
            'await tools.collaboration.spawn_agent.call(null, {});',
            'const dispatch = tools.collaboration.spawn_agent.bind(tools); await dispatch({});',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'cannot count dispatch'):
                self.wrapped_counts(source)

    def test_regex_literals_do_not_hide_or_invent_calls(self):
        for source, count in (
            ("const regex = /'/; await tools.multi_agent_v1__spawn_agent({});", 1),
            ('const regex = /["\\/]/g; await tools.multi_agent_v1__followup_task({});', 1),
            ('const regex = /tools.multi_agent_v1__spawn_agent({})/;', 0),
        ):
            with self.subTest(source=source):
                self.assertEqual(self.wrapped_counts(source)['total'], count)

    def test_non_exec_custom_tool_source_is_not_executed(self):
        self.assertEqual(self.wrapped_counts('+await tools.collaboration.spawn_agent({});', name='apply_patch')['total'], 0)

    def test_template_interpolation_requires_direct_native_calls(self):
        for source in ('text(`count=${results.length}`);',
                       'const source="tools.spawn_agent({})"; text(`${eval(source)}`);'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'template interpolation'):
                self.wrapped_counts(source)
        self.assertEqual(self.wrapped_counts(r'text(`example=\${not_an_expression}`);')['total'], 0)

    def test_ambiguous_slash_cannot_mask_a_dispatch(self):
        for source in (
            "{} /'/; await tools.multi_agent_v1__spawn_agent({}); // '",
            "if (true) /'/; await tools.multi_agent_v1__spawn_agent({}); // '",
            'value++ / 2; await tools.collaboration.spawn_agent({});',
            "let foo\n/'/; await tools.multi_agent_v1__spawn_agent({}); // '",
            'const x = value / 2; await tools.collaboration.spawn_agent({});',
            'const of=4; of / 2; await tools.spawn_agent({}); const x=3; x / 1;',
            'obj.return / 2; await tools.spawn_agent({}); obj.x / 1;',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'ambiguous slash'):
                self.wrapped_counts(source)

    def test_dynamic_code_rejected_even_without_literal_dispatch(self):
        for source in (
            'await import("data:text/javascript,tools.spawn_agent({})");',
            'await eval("tools.multi_agent_v1__spawn_agent({})");',
            'await eval("tools.multi_agent_v1__followup_task({})");',
            'await globalThis["eval"]("tools.multi_agent_v1__spawn_agent({})");',
            'const run = new Function("return tools.spawn_agent({})"); run();',
            'const run = (() => {})["constructor"]("return tools.spawn_agent({})"); run();',
            'const run = (() => {})["con" + "structor"]("return tools.spawn_agent({})"); run();',
            'const key = "constructor"; const run = (() => {})[key]; run("tools.spawn_agent({})")();',
            'const F = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(()=>{}), "constructor").value; F("return tools.spawn_agent({})")();',
            'const F = Object["getOwnPropertyDescriptors"](()=>{});',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'cannot count dispatch'):
                self.wrapped_counts(source)
        self.assertEqual(self.wrapped_counts('text(result.content[0]); text(result["content"]);')['total'], 0)

    def test_destructuring_extraction_fails_closed_as_a_syntax_class(self):
        patterns = (
            'const {"constructor": F} = Object;',
            'const {["constructor"]: F} = Object;',
            'const {["con" + "structor"]: F} = Object;',
            'const {[`constructor`]: F} = Object;',
            'const { /* key */ "constructor": F} /* binding */ = Object;',
            r'const {"constr\u0075ctor": F} = Object;',
            'let F; ({"constructor": F} = Object);',
            'let unused, {"constructor": F} = Object;',
            'const {nested: {"constructor": F}} = {nested: Object};',
            'const {"constructor": F = Object} = Object;',
            'const {...rest} = Object;',
            'const [F] = [Object];',
            'let F; [F] = [Object];',
            'for (const {"constructor": F} of [Object]) {}',
            'for ({"constructor": F} in {}) {}',
            'function run({"constructor": F}) {}',
            'const run = ({"constructor": F}) => F;',
            'const run = async ([F]) => F;',
            'const o = {run(a, {"constructor": F}) {}};',
            'const o = {"run"({["constructor"]: F}) {}};',
            'try {throw Object;} catch ({"constructor": F}) {}',
        )
        for pattern in patterns:
            source = pattern + ' F("return tools.spawn_agent({})")();'
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'cannot count dispatch'):
                self.wrapped_counts(source)
        # The same family must not authorize a hidden followup or zero-dispatch
        # extraction merely because no literal dispatch name survived lexing.
        for source in ('const {"constructor": F} = Object; F("return tools.followup_task({})")();',
                       'const {"content": value} = result;'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'cannot count dispatch'):
                self.wrapped_counts(source)

    def test_unbalanced_receipt_delimiters_fail_closed(self):
        for source in ('const {"constructor": F = Object;',
                       'text([1, 2);', 'await tools.spawn_agent({}); }'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'cannot count dispatch'):
                self.wrapped_counts(source)

    def test_literal_objects_and_arrays_are_not_binding_patterns(self):
        for source, count in (
            ('const data = {"content": result}; text(data["content"]);', 0),
            ('const data = [result]; text(data[0]);', 0),
            ('text({"example": "const {constructor: F} = Object"});', 0),
            ('function harmless(value = {"content": 1}, array = [1]) {}', 0),
            ('await tools.spawn_agent({"message": "example", items: [1, 2]});', 1),
            ('const a = await tools.spawn_agent({message: "a"}); '
             'await tools.followup_task({target: a.id, message: "b"});', 2),
        ):
            with self.subTest(source=source):
                self.assertEqual(self.wrapped_counts(source)['total'], count)

    def test_method_and_getter_calls_cannot_reuse_one_dispatch_site(self):
        for source in (
            'const o={run(){return tools.spawn_agent({});}}; o.run(); o.run();',
            'const o={"run"(){return tools.spawn_agent({});}}; o.run(); o.run();',
            'const o={["run"](){return tools.spawn_agent({});}}; o.run(); o.run();',
            'const o={get x(){return tools.spawn_agent({});}}; const a=o.x, b=o.x;',
            'class Task { result=tools.spawn_agent({}); } new Task(); new Task();',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'dynamic wrapper'):
                self.wrapped_counts(source)


class DispatchInputDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config.toml'
        self.config.write_text('[agents]\nmax_concurrent_threads_per_session=6\n', encoding='utf-8')
        self.trace = self.root / 'root.jsonl'
        self.trace.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': 'root'}}) + '\n', encoding='utf-8')
        self.state = self.root / 'state.json'
        self.valid = {'version': 1, 'root_thread_id': 'root', 'started_at': '2026-01-01T00:00:00Z',
                      'attempt_budget_N': 6, 'concurrency_cap_C': 6, 'greatest_observed_attempts': 0,
                      'rollouts': [str(self.trace)]}

    def invoke(self, value, expected_code):
        self.state.write_text(json.dumps(value), encoding='utf-8')
        before = self.state.read_bytes()
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('check_dispatch_budget.py')),
                                 '--state', str(self.state), '--config', str(self.config)],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stderr, '')
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'BLOCK_NEW_DISPATCH')
        self.assertEqual(payload['schema_version'], 1)
        self.assertEqual(payload['reason_code'], expected_code)
        self.assertEqual(self.state.read_bytes(), before)

    def test_malformed_state_shapes_are_json_errors_without_mutation(self):
        for value in ([], None, 1, {}, {**self.valid, 'rollouts': []},
                      {**self.valid, 'rollouts': [1]}, {**self.valid, 'rollouts': 'root.jsonl'},
                      {**self.valid, 'greatest_observed_attempts': []},
                      {**self.valid, 'started_at': 1}, {**self.valid, 'version': True}):
            with self.subTest(value=value):
                self.invoke(value, 'INVALID_STATE')

    def test_non_table_config_is_a_json_error(self):
        self.config.write_text('agents=[]\n', encoding='utf-8')
        self.invoke(self.valid, 'INVALID_CONFIG')

    def test_malformed_metadata_is_a_json_error(self):
        for value in ([], {'type': 'session_meta', 'payload': []},
                      {'type': 'session_meta', 'payload': {'id': []}}):
            with self.subTest(value=value):
                self.trace.write_text(json.dumps(value) + '\n', encoding='utf-8')
                self.invoke(self.valid, 'INVALID_ROLLOUT')

    def test_malformed_response_record_is_a_json_error(self):
        for value in ([], {'type': 'response_item', 'payload': []},
                      {'type': 'response_item', 'timestamp': 4, 'payload': {}},
                      {'type': 'response_item', 'timestamp': '2026-02-01T00:00:00Z',
                       'payload': {'type': 'function_call', 'name': 'spawn_agent', 'call_id': []}}):
            with self.subTest(value=value):
                self.trace.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': 'root'}})
                                      + '\n' + json.dumps(value) + '\n', encoding='utf-8')
                self.invoke(self.valid, 'TRACE_VALIDATION_FAILED')


if __name__ == '__main__':
    unittest.main()
