"""Acceptance examples for the advisory planner (including its real CLI)."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("planner", Path(__file__).with_name("plan_swarm.py"))
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
NOW = "2026-01-01T00:20:00+00:00"
ROOT = "11111111-1111-4111-8111-111111111111"


def row(aid, kind="operator", status="planned", wave=1, **kw):
    value = dict(attempt_id=aid, kind=kind, role=kind if kind in {"verifier", "reviewer"} else "default",
                 parent_attempt_id=None, depth=1, wave=wave, may_spawn_descendants=False,
                 descendant_budget=0, root_parent_thread_uuid=ROOT, root_parent_call_id=None,
                 delegated_by=dict(parent_thread_uuid=ROOT, parent_call_id=None),
                 execution_status=status, acceptance_status="pending", runtime_verified=False,
                 objective="Deliver bounded work " + aid, ownership=["work/" + aid],
                 acceptance_criteria=["C1"], evidence_locator="work/" + aid + "/receipt",
                 dependencies=[], integration_status="pending", deadline="2026-01-01T00:50:00Z")
    if status != "planned":
        value.update(root_parent_call_id="call-" + aid,
                     delegated_by=dict(parent_thread_uuid=ROOT, parent_call_id="call-" + aid),
                     started_at="2026-01-01T00:00:00Z")
    if status in P.TERMINAL:
        value.update(finished_at="2026-01-01T00:05:00Z", acceptance_status="excluded")
    if status == "completed":
        value.update(acceptance_status="accepted", runtime_verified=True,
                     thread_uuid="22222222-2222-4222-8222-222222222222",
                     runtime_turn="33333333-3333-4333-8333-333333333333",
                     parent_thread_uuid=ROOT, parent_call_id="call-" + aid,
                     runtime_model=P.CHECK.EXPECTED_MODEL, runtime_effort="low",
                     agent_role=value["role"], spawn_kind="spawn_agent", safety_enforcement="prompt_only")
    value.update(kw)
    return value


def ledger(rows=None, **kw):
    if rows is None:
        rows = [row("A", status="completed"), row("D", status="started"),
                row("B", wave=2, dependencies=["A"]), row("V", "verifier", wave=3)]
    value = dict(ledger_type="project", version=2, tree_id=ROOT,
                 run_id="44444444-4444-4444-8444-444444444444", assignments=rows,
                 attempt_budget_N=6, concurrency_cap_C=3, wave_width_W=2,
                 max_workflow_depth=1, verifier_reserve_V=1, phase="planning", closure_status="open",
                 root_integration_status="not_started", root_integration_receipt=None,
                 overall_deadline="2026-01-01T01:00:00Z", target_gate="LOCAL_PASS",
                 verified_gates=[], gate_receipts={}, external_authority=False)
    value.update(kw)
    return value


class PlannerTests(unittest.TestCase):
    def run_plan(self, value, opened=0, now=NOW):
        result = P.plan(value, opened, P.timestamp(now))
        self.assertNotIn("errors", result, result)
        return result

    def codes(self, result, aid):
        return {x["code"] for b in result["blocked"] if b["attempt_id"] == aid for x in b["reasons"]}

    def test_rolling_ready_while_independent_work_active(self):
        result = self.run_plan(ledger())
        self.assertEqual(result["selected_attempt_ids"], ["B"])
        self.assertEqual(result["active_attempt_ids"], ["D"])
        self.assertEqual(result["integration_pending_attempt_ids"], ["A"])
        self.assertEqual(result["next_wave"], 2)

    def test_failed_and_unaccepted_dependencies(self):
        for state, acceptance, code in [("failed", "excluded", "DEPENDENCY_FAILED"),
                                        ("completed", "rejected", "DEPENDENCY_NOT_ACCEPTED")]:
            value = ledger()
            value["assignments"][0].update(execution_status=state, acceptance_status=acceptance)
            result = self.run_plan(value)
            self.assertIn(code, self.codes(result, "B"))
            self.assertNotIn("B", result["selected_attempt_ids"])

    def test_ordinary_reviewer_can_start_after_accepted_work(self):
        value = ledger()
        value["assignments"][2].update(kind="reviewer", role="reviewer", ownership=["read-only"])
        self.assertEqual(self.run_plan(value)["selected_attempt_ids"], ["B"])

    def test_builder_review_then_acceptance_unlocks_consumer(self):
        rows = [row("A", kind="builder"),
                row("R", kind="reviewer", wave=2, role="reviewer", ownership=["read-only"], dependencies=["A"]),
                row("B", kind="builder", wave=3, dependencies=["A", "R"]),
                row("V", "verifier", wave=4)]
        value = ledger(rows)
        self.assertEqual(self.run_plan(value)["selected_attempt_ids"], ["A"])
        rows[0] = row("A", "builder", "completed", acceptance_status="pending")
        result = self.run_plan(value)
        self.assertEqual(result["selected_attempt_ids"], ["R"])
        self.assertIn("DEPENDENCY_NOT_ACCEPTED", self.codes(result, "B"))
        before = copy.deepcopy(value)
        self.run_plan(value)
        self.assertEqual(value, before)
        rows[0]["acceptance_status"] = "accepted"
        rows[1] = row("R", "reviewer", "completed", wave=2, dependencies=["A"], ownership=["read-only"],
                      started_at="2026-01-01T00:06:00Z", finished_at="2026-01-01T00:10:00Z")
        self.assertEqual(self.run_plan(value)["selected_attempt_ids"], ["B"])

    def test_future_dependency_finish_and_planned_time(self):
        value = ledger()
        value["assignments"][0]["finished_at"] = "2026-01-01T00:25:00Z"
        self.assertIn("DEPENDENCY_FINISH_FUTURE", self.codes(self.run_plan(value), "B"))
        value = ledger()
        value["assignments"][2]["planned_at"] = "2026-01-01T00:25:00Z"
        self.assertIn("PLANNED_AT_FUTURE", self.codes(self.run_plan(value), "B"))

    def test_path_alias_live_and_competing_planned_writers(self):
        value = ledger()
        value["assignments"][1]["ownership"] = ["C:/Repo/SRC"]
        value["assignments"][2]["ownership"] = ["c:\\repo\\src\\.\\module"]
        result = self.run_plan(value)
        self.assertIn("WRITER_OWNERSHIP_CONFLICT", self.codes(result, "B"))
        rows = [row("A", ownership=["src"]), row("B", ownership=["SRC/file"]),
                row("V", "verifier", wave=2)]
        result = self.run_plan(ledger(rows))
        self.assertEqual(result["selected_attempt_ids"], ["A"])
        self.assertIn("WRITER_OWNERSHIP_CONFLICT", self.codes(result, "B"))

    def test_capacity_uses_max_and_wave_width(self):
        result = self.run_plan(ledger(), opened=3)
        self.assertEqual(result["selected_attempt_ids"], [])
        self.assertEqual(result["capacity"]["effective_open_children"], 3)
        result = self.run_plan(ledger(), opened=0)
        self.assertEqual(result["capacity"]["effective_open_children"], 1)
        rows = [row("A"), row("B"), row("C", wave=2), row("V", "verifier", wave=3)]
        self.assertEqual(self.run_plan(ledger(rows))["selected_attempt_ids"], ["A", "B"])

    def test_failed_verifier_keeps_required_reserve(self):
        rows = [row("F", "verifier", "failed"), row("X", "verifier", "failed"),
                row("A", wave=2), row("V", "verifier", wave=3)]
        result = self.run_plan(ledger(rows, attempt_budget_N=4))
        # Two failed attempts leave two slots: one ordinary and one accepted-verifier reserve.
        self.assertEqual(result["selected_attempt_ids"], ["A"])
        self.assertEqual(result["capacity"]["verifier_reserve_remaining"], 1)
        rows.insert(3, row("B", wave=2))
        # A realistic exhausted budget can omit another future verifier, but retain failed reserve rows.
        rows.pop()
        result = self.run_plan(ledger(rows, attempt_budget_N=4))
        self.assertIn("VERIFIER_RESERVE_PROTECTED", self.codes(result, "B"))

    def test_candidate_reviewer_does_not_spend_final_verifier_reserve(self):
        rows = [row("R", "reviewer", "completed", ownership=["read-only"]),
                row("F", "verifier", "failed"), row("A", wave=2), row("B", wave=2)]
        result = self.run_plan(ledger(rows, attempt_budget_N=4))
        self.assertEqual(result["capacity"]["verifier_reserve_remaining"], 1)
        self.assertEqual(result["selected_attempt_ids"], ["A"])
        self.assertIn("VERIFIER_RESERVE_PROTECTED", self.codes(result, "B"))

    def test_hierarchical_mode_with_only_root_leaves_is_still_unsupported(self):
        result = P.plan(ledger(mode="hierarchical"), 0, P.timestamp(NOW))
        self.assertIn("errors", result)
        self.assertNotIn("selected_attempt_ids", result)

    def test_integration_before_final_verifier_and_future_verifier_not_required(self):
        rows = [row("A", status="completed"), row("V", "verifier", wave=2),
                row("V2", "verifier", wave=2)]
        value = ledger(rows, root_integration_status="completed", root_integration_receipt="receipt:root")
        self.assertIn("ACCEPTED_WRITERS_NOT_INTEGRATED", self.codes(self.run_plan(value), "V"))
        rows[0]["integration_status"] = "integrated"
        self.assertEqual(self.run_plan(value)["selected_attempt_ids"], ["V", "V2"])
        rows[0].update(integration_status="pending", acceptance_status="pending")
        self.assertIn("NON_VERIFIER_WORK_UNFINISHED", self.codes(self.run_plan(value), "V"))

    def test_expired_active_writer_never_releases_ownership_or_slot(self):
        value = ledger()
        value["assignments"][1].update(deadline="2026-01-01T00:10:00Z", ttl_seconds=60)
        value["assignments"][2]["ownership"] = ["work/D/child"]
        result = self.run_plan(value)
        self.assertEqual(result["active_attempt_ids"], ["D"])
        self.assertIn("WRITER_OWNERSHIP_CONFLICT", self.codes(result, "B"))
        self.assertEqual({r["code"] for r in result["active_alerts"][0]["reasons"]},
                         {"DEADLINE_EXPIRED", "ACTIVE_TTL_EXPIRED"})
        self.assertIn("OVERALL_DEADLINE_EXPIRED", self.codes(self.run_plan(value, now="2026-01-01T02:00:00Z"), "B"))

    def test_future_terminal_writer_and_expired_planned_work(self):
        value = ledger()
        value["assignments"][0]["finished_at"] = "2026-01-01T00:25:00Z"
        value["assignments"][2].update(dependencies=[], ownership=["WORK/a/next"])
        result = self.run_plan(value)
        self.assertIn("WRITER_OWNERSHIP_CONFLICT", self.codes(result, "B"))
        value = ledger()
        value["assignments"][2]["deadline"] = "2026-01-01T00:10:00Z"
        self.assertIn("DEADLINE_EXPIRED", self.codes(self.run_plan(value), "B"))

    def test_future_terminal_attempt_still_occupies_capacity_at_snapshot(self):
        rows = [row("A", status="completed", finished_at="2026-01-01T00:25:00Z"),
                row("B", wave=2), row("V", "verifier", wave=3)]
        value = ledger(rows, concurrency_cap_C=1, wave_width_W=1, attempt_budget_N=4)
        result = self.run_plan(value)
        self.assertEqual(result["selected_attempt_ids"], [])
        self.assertEqual(result["active_attempt_ids"], ["A"])
        self.assertEqual(result["capacity"]["effective_open_children"], 1)
        self.assertIn("CAPACITY_OR_WAVE_LIMIT", self.codes(result, "B"))
        self.assertEqual(result["active_alerts"][0]["reasons"],
                         [P.reason("RECORDED_FINISH_AFTER_SNAPSHOT")])
        self.assertEqual(self.run_plan(value, now="2026-01-01T00:25:00Z")["selected_attempt_ids"], ["B"])

    def test_terminal_historical_writer_needs_external_actual_release_check(self):
        value = ledger()
        value["assignments"][2]["ownership"] = ["work/a/next"]
        result = self.run_plan(value)
        self.assertEqual(result["selected_attempt_ids"], ["B"])
        self.assertIn("ROOT_CONFIRM_ACTUAL_WRITER_RELEASE_BEFORE_REASSIGNMENT", result["required_checks"])

    def test_retry_waits_for_predecessor_and_checks_recovery(self):
        rows = [row("A", status="started", epoch=1, dedup_key="a", retry_owner="root"),
                row("B", wave=2, retry_of="A", epoch=2, dedup_key="a", retry_owner="root"),
                row("V", "verifier", wave=3)]
        value = ledger(rows)
        self.assertIn("RETRY_PREDECESSOR_NOT_FINISHED", self.codes(self.run_plan(value), "B"))
        rows[0].update(execution_status="failed", acceptance_status="excluded", finished_at="2026-01-01T00:05:00Z")
        self.assertEqual(self.run_plan(value)["selected_attempt_ids"], ["B"])
        rows[1]["epoch"] = 1
        self.assertIn("errors", P.plan(value, 0, P.timestamp(NOW)))

    def cli(self, payload, *args):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            path.write_bytes(raw)
            proc = subprocess.run([sys.executable, str(Path(P.__file__)), "--ledger-json", str(path),
                                   "--open-children", "0", "--now", NOW, *args], capture_output=True, text=True)
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(proc.stderr, "")
        return proc.returncode, json.loads(proc.stdout)

    def recovery_fixture(self):
        rows = [row("O", status="timed_out", epoch=1, dedup_key="work", retry_owner="root"),
                row("N", status="completed", wave=2, epoch=2, retry_of="O", dedup_key="work", retry_owner="root",
                    started_at="2026-01-01T00:06:00Z", finished_at="2026-01-01T00:12:00Z"),
                row("B", wave=3, dependencies=["O"]), row("V", "verifier", wave=4)]
        return ledger(rows)

    def test_retry_hint_requires_explicit_rebinding_and_preserves_input(self):
        value = self.recovery_fixture()
        before = copy.deepcopy(value)
        code, result = self.cli(value)
        self.assertEqual(code, 0)
        self.assertNotIn("B", result["selected_attempt_ids"])
        self.assertIn("DEPENDENCY_FAILED", self.codes(result, "B"))
        self.assertEqual(result["dependency_replacement_hints"], [dict(
            attempt_id="B", dependency_attempt_id="O", requires_root_review=True,
            candidates=[dict(attempt_id="N", requires_ledger_reordering=False)])])
        self.assertEqual(value, before)
        value["assignments"][2]["dependencies"] = ["N"]
        result = self.run_plan(value)
        self.assertIn("B", result["selected_attempt_ids"])
        self.assertEqual(result["dependency_replacement_hints"], [])

    def test_retry_hint_filters_unaccepted_future_and_unrelated_attempts(self):
        changes = [dict(acceptance_status="pending"), dict(acceptance_status="rejected"),
                   dict(execution_status="failed", acceptance_status="excluded"),
                   dict(execution_status="started", acceptance_status="pending", finished_at=None),
                   dict(finished_at="2026-01-01T00:25:00Z"), dict(retry_of=None)]
        for change in changes:
            with self.subTest(change=change):
                value = self.recovery_fixture()
                value["assignments"][1].update(change)
                result = self.run_plan(value)
                self.assertEqual(result["dependency_replacement_hints"], [])
                self.assertNotIn("B", result["selected_attempt_ids"])
        value = self.recovery_fixture()
        self.assertTrue(self.run_plan(value, now="2026-01-01T00:12:00Z")["dependency_replacement_hints"])

    def test_retry_hint_marks_later_rows_without_reordering_or_duplicate_hints(self):
        value = self.recovery_fixture()
        rows = value["assignments"]
        rows[1], rows[2] = rows[2], rows[1]
        rows[1]["dependencies"] = ["O", "O"]
        before = copy.deepcopy(value)
        result = self.run_plan(value)
        self.assertEqual(len(result["dependency_replacement_hints"]), 1)
        self.assertEqual(result["dependency_replacement_hints"][0]["candidates"],
                         [dict(attempt_id="N", requires_ledger_reordering=True)])
        self.assertEqual(value, before)
        # Editing the ID alone would violate ledger order; the hint grants no repair authority.
        rows[1]["dependencies"] = ["N"]
        self.assertIn("errors", P.plan(value, 0, P.timestamp(NOW)))

    def test_transitive_retry_hints_keep_all_legacy_candidates_for_root_review(self):
        value = self.recovery_fixture()
        value["retry_limit"] = 2
        rows = value["assignments"]
        rows[1].pop("epoch")  # Legacy records do not prove newer-generation invalidation.
        successor = row("NN", status="completed", wave=3, retry_of="N", dedup_key="work", retry_owner="root",
                        started_at="2026-01-01T00:13:00Z", finished_at="2026-01-01T00:17:00Z",
                        thread_uuid="55555555-5555-4555-8555-555555555555",
                        runtime_turn="66666666-6666-4666-8666-666666666666")
        rows.insert(2, successor)
        rows[3]["wave"], rows[4]["wave"] = 4, 5
        result = self.run_plan(value)
        hint = result["dependency_replacement_hints"][0]
        self.assertEqual([c["attempt_id"] for c in hint["candidates"]], ["N", "NN"])
        self.assertTrue(hint["requires_root_review"])
        self.assertNotIn("B", result["selected_attempt_ids"])
        rows[1].update(execution_status="failed", acceptance_status="excluded")
        result = self.run_plan(value)
        self.assertEqual([c["attempt_id"] for c in result["dependency_replacement_hints"][0]["candidates"]], ["NN"])

    def test_explicit_sol_profile_and_repeat_call_isolation(self):
        value = ledger()
        value["assignments"][0]["runtime_model"] = "gpt-6.1-sol"
        before = copy.deepcopy(value)
        self.assertIn("errors", P.plan(value, 0, P.timestamp(NOW)))
        result = P.plan(value, 0, P.timestamp(NOW), specialist_model="gpt-6.1-sol")
        self.assertEqual(result["selected_attempt_ids"], ["B"])
        self.assertIn("errors", P.plan(value, 0, P.timestamp(NOW)))
        self.assertNotIn("errors", P.plan(ledger(), 0, P.timestamp(NOW)))
        self.assertEqual(P.CHECK.EXPECTED_MODEL, "gpt-6-luna")
        self.assertEqual(value, before)
        self.assertEqual(self.cli(value)[0], 2)
        self.assertEqual(self.cli(value, "--specialist-model", "gpt-6.1-sol")[0], 0)

    def test_explicit_profile_rejects_mixed_mismatch_and_effort(self):
        for model, effort in [("gpt-6-luna", "low"), ("gpt-6.1-sol", "high")]:
            value = ledger()
            value["assignments"][0].update(runtime_model=model, runtime_effort=effort)
            self.assertIn("errors", P.plan(value, 0, P.timestamp(NOW), specialist_model="gpt-6.1-sol"))
        value = ledger([row("A", status="completed", runtime_model="gpt-6.1-sol"),
                        row("D", status="completed"), row("V", "verifier", wave=2)])
        self.assertIn("errors", P.plan(value, 0, P.timestamp(NOW), specialist_model="gpt-6.1-sol"))
        with self.assertRaises(ValueError):
            P.plan(ledger(), 0, P.timestamp(NOW), specialist_model="unsupported")
        code, output = self.cli(ledger(), "--specialist-model", "unsupported")
        self.assertEqual(code, 2)
        self.assertEqual(output["errors"][0]["code"], "INVALID_INPUT")
        self.assertNotIn("selected_attempt_ids", output)
        self.assertNotIn("errors", P.plan(ledger(), 0, P.timestamp(NOW)))

    def test_cli_determinism_and_unchanged_input(self):
        a = self.cli(ledger())
        b = self.cli(ledger())
        self.assertEqual(a, b)
        self.assertEqual(a[0], 0)
        self.assertTrue(a[1]["advisory_only"])

    def test_standalone_cli_does_not_write_bytecode_or_input(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name in ("plan_swarm.py", "check_setup.py", "check_dispatch_budget.py"):
                shutil.copyfile(Path(P.__file__).with_name(name), directory / name)
            (directory / "ledger.json").write_text(json.dumps(ledger()), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            env = dict(os.environ)
            env.pop("PYTHONDONTWRITEBYTECODE", None)
            result = subprocess.run([sys.executable, str(directory / "plan_swarm.py"),
                                     "--ledger-json", str(directory / "ledger.json"),
                                     "--open-children", "0", "--now", NOW],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)

    def test_cli_invalid_input_is_structured_without_partial_selection(self):
        cases = [b"{", [], ledger(version=1), ledger(ledger_type="research"),
                 ledger([row("A", dependencies=[["nested"]])]),
                 ledger([row("A", dependencies=["A"])]),
                 ledger([row("A", parent_attempt_id="A", depth=2)]),
                 ledger([row("A", acceptance_status={"bad": 1})])]
        for value in cases:
            with self.subTest(value=value):
                code, result = self.cli(value)
                self.assertEqual(code, 2)
                self.assertIn("errors", result)
                self.assertNotIn("selected_attempt_ids", result)
        for args in [("--now", "2026-01-01T00:20:00"), ("--open-children", "-1"),
                     ("--open-children", "true")]:
            self.assertEqual(self.cli(ledger(), *args)[0], 2)
        with self.assertRaises(ValueError):
            P.plan(ledger(), True, P.timestamp(NOW))


if __name__ == "__main__":
    unittest.main()
