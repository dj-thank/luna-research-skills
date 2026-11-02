import importlib.util
import json
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

    def test_benign_template_expression_is_not_dispatch(self):
        self.assertEqual(self.wrapped_counts('text(`count=${results.length}`);')['total'], 0)

    def test_ambiguous_slash_cannot_mask_a_dispatch(self):
        for source in (
            "{} /'/; await tools.multi_agent_v1__spawn_agent({}); // '",
            "if (true) /'/; await tools.multi_agent_v1__spawn_agent({}); // '",
            'value++ / 2; await tools.collaboration.spawn_agent({});',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'ambiguous slash'):
                self.wrapped_counts(source)
        self.assertEqual(self.wrapped_counts('const x = value / 2; await tools.collaboration.spawn_agent({});')['total'], 1)


if __name__ == '__main__':
    unittest.main()
