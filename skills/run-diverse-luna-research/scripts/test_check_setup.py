from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid


SCRIPT_PATH = Path(__file__).with_name("check_setup.py")
SPEC = importlib.util.spec_from_file_location("luna_check_setup", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def rollout_records(
    thread_id: str,
    turn_id: str,
    *,
    sandbox: str = "read-only",
    completed: bool = True,
    role: str = "default",
    parent_id: str | None = None,
) -> list[dict[str, object]]:
    parent_id = parent_id or str(uuid.uuid4())
    records: list[dict[str, object]] = [
        {
            "type": "session_meta",
            "payload": {
                "id": thread_id,
                "parent_thread_id": parent_id,
                "thread_source": "subagent",
                "agent_role": role,
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "depth": 1,
                            "parent_thread_id": parent_id,
                            "agent_role": role,
                            "agent_path": "/root/test_assignment",
                        }
                    }
                },
            },
        },
        {
            "type": "turn_context",
            "payload": {
                "turn_id": turn_id,
                "model": "gpt-5.6-luna",
                "effort": "medium",
                "sandbox_policy": {"type": sandbox},
            },
        },
    ]
    if completed:
        records.append(
            {
                "type": "event_msg",
                "payload": {"type": "task_complete", "turn_id": turn_id},
            }
        )
    return records


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    text = "\n".join(json.dumps(record) for record in records) + "\n"
    path.write_text(text, encoding="utf-8")


def assignment(
    attempt_id: str,
    quota: str,
    *,
    priority: bool = True,
    status: str = "planned",
    acceptance: str = "pending",
    runtime_verified: bool = False,
    thread_uuid: str | None = None,
    overlap_key: str | None = None,
    coverage_cell: str | None = None,
    retry_of: str | None = None,
    gap_reason: str | None = None,
    source_plane: str = "public_web",
    access_mode: str = "prompt_only_public",
    safety_enforcement: str | None = None,
) -> dict[str, object]:
    accepted = acceptance == "accepted"
    return {
        "attempt_id": attempt_id,
        "coverage_cell": coverage_cell or f"cell {attempt_id}",
        "priority": priority,
        "quota_label": quota,
        "source_plane": source_plane,
        "access_mode": access_mode,
        "source_universe": f"universe {attempt_id}",
        "exclusion_rule": "exclude mirrors",
        "overlap_key": overlap_key or f"key-{attempt_id}",
        "retry_of": retry_of,
        "deadline": "2026-08-16T11:00:00+09:00",
        "execution_status": status,
        "acceptance_status": acceptance,
        "thread_uuid": thread_uuid,
        "runtime_turn": str(uuid.uuid4()) if accepted else None,
        "agent_role": "default" if accepted else None,
        "runtime_model": "gpt-5.6-luna" if accepted else None,
        "runtime_effort": "medium" if accepted else None,
        "parent_thread_uuid": str(uuid.uuid4()) if accepted else None,
        "parent_call_id": "call-test" if accepted else None,
        "spawn_kind": "spawn_agent" if accepted else None,
        "safety_enforcement": safety_enforcement
        or ("prompt_only" if accepted else "unknown"),
        "runtime_verified": runtime_verified,
        "gap_reason": gap_reason,
    }


def project_assignment(
    attempt_id: str,
    kind: str,
    *,
    status: str = "planned",
    acceptance: str = "pending",
    ownership: list[str] | None = None,
    dependencies: list[str] | None = None,
    integration_status: str = "not_applicable",
) -> dict[str, object]:
    accepted = acceptance == "accepted"
    return {
        "attempt_id": attempt_id,
        "kind": kind,
        "objective": f"objective {attempt_id}",
        "ownership": ownership or ["read-only"],
        "dependencies": dependencies or [],
        "deadline": "2026-08-16T11:00:00+09:00",
        "execution_status": status,
        "acceptance_status": acceptance,
        "acceptance_criteria": ["observable result"],
        "evidence_locator": f"receipt:{attempt_id}",
        "integration_status": integration_status,
        "thread_uuid": str(uuid.uuid4()) if accepted else None,
        "runtime_turn": str(uuid.uuid4()) if accepted else None,
        "agent_role": "default" if accepted else None,
        "runtime_model": "gpt-5.6-luna" if accepted else None,
        "runtime_effort": "medium" if accepted else None,
        "parent_thread_uuid": str(uuid.uuid4()) if accepted else None,
        "parent_call_id": "call-test" if accepted else None,
        "spawn_kind": "spawn_agent" if accepted else None,
        "safety_enforcement": "prompt_only" if accepted else "unknown",
        "runtime_verified": accepted,
    }


class SpawnSchemaTests(unittest.TestCase):
    def test_properties_prefers_nonempty_parameters_over_empty_input_schema(self) -> None:
        schema = {
            "name": "spawn_agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {"type": "string"},
                    "message": {"type": "string"},
                    "fork_turns": {"enum": ["none", "all"]},
                },
                "required": ["task_name", "message"],
            },
            "inputSchema": {"type": "object", "properties": {}},
        }
        properties = CHECK.spawn_agent_properties(schema)
        self.assertIn("message", properties)
        self.assertIn("fork_turns", properties)

    def test_validator_never_unions_incomplete_schema_variants(self) -> None:
        document = {
            "tools": [
                {
                    "name": "spawn_agent",
                    "parameters": {
                        "properties": {
                            "task_name": {"type": "string"},
                            "message": {"type": "string"},
                            "agent_type": {"enum": ["default"]},
                        },
                        "required": ["task_name", "message"],
                    },
                },
                {
                    "name": "spawn_agent",
                    "parameters": {
                        "properties": {
                            "task_name": {"type": "string"},
                            "message": {"type": "string"},
                            "fork_context": {"enum": [False]},
                        },
                        "required": ["task_name", "message"],
                    },
                },
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schema.json"
            write_json(path, document)
            errors, _ = CHECK.validate_spawn_schema(path, "default")
        self.assertTrue(errors)

    def test_validator_rejects_fork_turns_without_none(self) -> None:
        document = {
            "name": "spawn_agent",
            "parameters": {
                "properties": {
                    "task_name": {"type": "string"},
                    "message": {"type": "string"},
                    "agent_type": {"enum": ["default"]},
                    "fork_turns": {"enum": ["all", "3"]},
                },
                "required": ["task_name", "message"],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schema.json"
            write_json(path, document)
            errors, _ = CHECK.validate_spawn_schema(path, "default")
        self.assertTrue(errors)

    def test_validator_accepts_complete_route_in_one_variant(self) -> None:
        document = {
            "name": "spawn_agent",
            "parameters": {
                "properties": {
                    "task_name": {"type": "string"},
                    "message": {"type": "string"},
                    "agent_type": {"enum": ["default"]},
                    "fork_turns": {"enum": ["none", "all"]},
                },
                "required": ["task_name", "message"],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schema.json"
            write_json(path, document)
            errors, _ = CHECK.validate_spawn_schema(path, "default")
        self.assertEqual(errors, [])

    def test_validator_rejects_optional_base_request_fields(self) -> None:
        document = {
            "name": "spawn_agent",
            "parameters": {
                "properties": {
                    "task_name": {"type": "string"},
                    "message": {"type": "string"},
                    "agent_type": {"enum": ["default"]},
                    "fork_turns": {"enum": ["none"]},
                },
                "required": [],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schema.json"
            write_json(path, document)
            errors, _ = CHECK.validate_spawn_schema(path, "default")
        self.assertTrue(errors)

    def test_validator_rejects_impossible_route_types(self) -> None:
        document = {
            "name": "spawn_agent",
            "parameters": {
                "properties": {
                    "task_name": {"type": "string"},
                    "message": {"type": "string"},
                    "agent_type": {"type": "integer"},
                    "fork_turns": {"type": "integer"},
                },
                "required": ["task_name", "message"],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schema.json"
            write_json(path, document)
            errors, _ = CHECK.validate_spawn_schema(path, "default")
        self.assertTrue(errors)

    def test_validator_honors_string_pattern(self) -> None:
        document = {
            "name": "spawn_agent",
            "parameters": {
                "properties": {
                    "task_name": {"type": "string"},
                    "message": {"type": "string"},
                    "agent_type": {"type": "string", "pattern": "^worker$"},
                    "fork_turns": {"type": "string", "pattern": "^none$"},
                },
                "required": ["task_name", "message"],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schema.json"
            write_json(path, document)
            errors, _ = CHECK.validate_spawn_schema(path, "default")
        self.assertTrue(errors)


class RuntimeReceiptTests(unittest.TestCase):
    def test_completed_read_only_runtime_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(
                path,
                rollout_records(str(uuid.uuid4()), str(uuid.uuid4())),
            )
            errors, warnings = CHECK.validate_runtime_rollout(
                path, "default", require_read_only=True
            )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_latest_turn_requires_matching_task_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
            records.append(
                {
                    "type": "turn_context",
                    "payload": {
                        "turn_id": str(uuid.uuid4()),
                        "model": "gpt-5.6-luna",
                        "effort": "medium",
                        "sandbox_policy": {"type": "read-only"},
                    },
                }
            )
            write_jsonl(path, records)
            errors, _ = CHECK.validate_runtime_rollout(path, "default")
        self.assertTrue(any("task_complete" in error for error in errors))

    def test_exact_turn_receipt_is_selected_in_followup_rollout(self) -> None:
        thread_id = str(uuid.uuid4())
        first_turn = str(uuid.uuid4())
        second_turn = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            records = rollout_records(thread_id, first_turn)
            records.extend(
                [
                    {
                        "type": "turn_context",
                        "payload": {
                            "turn_id": second_turn,
                            "model": "gpt-5.6-terra",
                            "effort": "medium",
                            "sandbox_policy": {"type": "read-only"},
                        },
                    },
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "turn_id": second_turn,
                        },
                    },
                ]
            )
            write_jsonl(path, records)
            exact_errors, _ = CHECK.validate_runtime_rollout(
                path, "default", runtime_turn=first_turn
            )
            latest_errors, _ = CHECK.validate_runtime_rollout(path, "default")
        self.assertEqual(exact_errors, [])
        self.assertTrue(any("runtime model" in error for error in latest_errors))

    def test_require_read_only_rejects_prompt_only_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(
                path,
                rollout_records(
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    sandbox="danger-full-access",
                ),
            )
            errors, _ = CHECK.validate_runtime_rollout(
                path, "default", require_read_only=True
            )
        self.assertTrue(any("read-only" in error for error in errors))

    def test_duplicate_rollouts_are_ambiguous(self) -> None:
        thread_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as temp:
            codex_home = Path(temp)
            for name in ("a", "b"):
                directory = codex_home / "sessions" / name
                directory.mkdir(parents=True)
                path = directory / f"rollout-{thread_id}.jsonl"
                write_jsonl(path, rollout_records(thread_id, str(uuid.uuid4())))
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                CHECK.find_runtime_rollout(codex_home, thread_id)

    def test_latest_turn_must_be_a_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(path, rollout_records(str(uuid.uuid4()), "not-a-uuid"))
            errors, _ = CHECK.validate_runtime_rollout(
                path, "default", require_read_only=True
            )
        self.assertTrue(any("not a UUID" in error for error in errors))

    def test_completion_must_follow_turn_context(self) -> None:
        thread_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        records = rollout_records(thread_id, turn_id)
        reordered = [records[0], records[2], records[1]]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(path, reordered)
            errors, _ = CHECK.validate_runtime_rollout(path, "default")
        self.assertTrue(any("after its turn_context" in error for error in errors))

    def test_runtime_requires_parent_depth_role_and_path(self) -> None:
        records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        spawn = records[0]["payload"]["source"]["subagent"]["thread_spawn"]
        spawn.pop("agent_path")
        spawn["depth"] = 0
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(path, records)
            errors, _ = CHECK.validate_runtime_rollout(path, "default")
        self.assertTrue(any("depth" in error for error in errors))
        self.assertTrue(any("agent_path" in error for error in errors))

    def test_lookup_falls_back_to_session_meta_when_filename_is_unrelated(self) -> None:
        thread_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as temp:
            codex_home = Path(temp)
            directory = codex_home / "sessions" / "x"
            directory.mkdir(parents=True)
            path = directory / "random.jsonl"
            write_jsonl(path, rollout_records(thread_id, str(uuid.uuid4())))
            resolved = CHECK.find_runtime_rollout(codex_home, thread_id)
        self.assertEqual(resolved, path.resolve())

    def test_duplicate_turn_context_is_rejected(self) -> None:
        thread_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        records = rollout_records(thread_id, turn_id)
        records.insert(2, records[1])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(path, records)
            errors, _ = CHECK.validate_runtime_rollout(path, "default")
        self.assertTrue(any("turn_context records" in error for error in errors))

    def test_parent_spawn_request_is_bound_to_child(self) -> None:
        child_records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        child_meta = child_records[0]["payload"]
        parent_id = child_meta["parent_thread_id"]
        parent_records = [
            {"type": "session_meta", "payload": {"id": parent_id}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "call-test",
                    "arguments": json.dumps(
                        {
                            "task_name": "test_assignment",
                            "message": "bounded task",
                            "agent_type": "default",
                            "fork_turns": "none",
                        }
                    ),
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent_path = Path(temp) / "parent.jsonl"
            child_path = Path(temp) / "child.jsonl"
            write_jsonl(parent_path, parent_records)
            write_jsonl(child_path, child_records)
            errors, _ = CHECK.validate_spawn_provenance(
                parent_path, child_path, "default"
            )
            mismatch_errors, _ = CHECK.validate_spawn_provenance(
                parent_path, child_path, "default", "call-other"
            )
        self.assertEqual(errors, [])
        self.assertTrue(any("call_id" in error for error in mismatch_errors))

    def test_parent_full_history_spawn_is_rejected(self) -> None:
        child_records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        child_meta = child_records[0]["payload"]
        parent_records = [
            {"type": "session_meta", "payload": {"id": child_meta["parent_thread_id"]}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "arguments": json.dumps(
                        {
                            "task_name": "test_assignment",
                            "message": "bounded task",
                            "agent_type": "default",
                            "fork_turns": "all",
                        }
                    ),
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent_path = Path(temp) / "parent.jsonl"
            child_path = Path(temp) / "child.jsonl"
            write_jsonl(parent_path, parent_records)
            write_jsonl(child_path, child_records)
            errors, _ = CHECK.validate_spawn_provenance(
                parent_path, child_path, "default"
            )
        self.assertTrue(any("fork_turns" in error for error in errors))

    def test_parent_default_role_must_be_explicit(self) -> None:
        child_records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        child_meta = child_records[0]["payload"]
        parent_records = [
            {"type": "session_meta", "payload": {"id": child_meta["parent_thread_id"]}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "call-test",
                    "arguments": json.dumps(
                        {
                            "task_name": "test_assignment",
                            "message": "bounded task",
                            "fork_turns": "none",
                        }
                    ),
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent_path = Path(temp) / "parent.jsonl"
            child_path = Path(temp) / "child.jsonl"
            write_jsonl(parent_path, parent_records)
            write_jsonl(child_path, child_records)
            errors, _ = CHECK.validate_spawn_provenance(
                parent_path, child_path, "default"
            )
        self.assertTrue(any("explicitly selected" in error for error in errors))


class LedgerTests(unittest.TestCase):
    def test_feasible_planning_ledger_passes(self) -> None:
        ledger = {
            "version": 1,
            "phase": "planning",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                assignment("R-01", "primary"),
                assignment("R-02", "adversarial"),
                assignment("R-03", "measurement_gap"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertEqual(errors, [])

    def test_uncovered_priority_cell_blocks_synthesis(self) -> None:
        thread_id = str(uuid.uuid4())
        ledger = {
            "version": 1,
            "phase": "synthesis",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                assignment(
                    "R-01",
                    "primary",
                    status="completed",
                    acceptance="accepted",
                    runtime_verified=True,
                    thread_uuid=thread_id,
                ),
                assignment(
                    "R-02",
                    "adversarial",
                    status="failed",
                    acceptance="excluded",
                ),
                assignment(
                    "R-03",
                    "measurement_gap",
                    status="failed",
                    acceptance="excluded",
                    gap_reason="No current primary measurement source was accessible.",
                ),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertTrue(any("key-R-02" in error for error in errors))

    def test_accepted_result_requires_runtime_receipt(self) -> None:
        ledger = {
            "version": 1,
            "phase": "synthesis",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                assignment(
                    "R-01",
                    "primary",
                    status="completed",
                    acceptance="accepted",
                    gap_reason="",
                ),
                assignment(
                    "R-02",
                    "adversarial",
                    status="failed",
                    acceptance="excluded",
                    gap_reason="No independent source.",
                ),
                assignment(
                    "R-03",
                    "measurement_gap",
                    status="failed",
                    acceptance="excluded",
                    gap_reason="No measurement source.",
                ),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertTrue(any("runtime_verified=true" in error for error in errors))

    def test_quota_cannot_use_duplicate_coverage_cells(self) -> None:
        ledger = {
            "version": 1,
            "phase": "planning",
            "N": 10,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                assignment(
                    "R-01", "primary", coverage_cell="same primary claim"
                ),
                assignment(
                    "R-02",
                    "primary",
                    coverage_cell="same primary claim",
                    overlap_key="different-key",
                ),
                assignment("R-03", "adversarial"),
                assignment("R-04", "adversarial"),
                assignment("R-05", "measurement_gap"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertTrue(any("coverage_cell" in error for error in errors))
        self.assertTrue(any("quota primary" in error for error in errors))

    def test_root_only_row_cannot_accept_child_runtime(self) -> None:
        row = assignment(
            "R-01",
            "primary",
            status="completed",
            acceptance="accepted",
            runtime_verified=True,
            thread_uuid=str(uuid.uuid4()),
            access_mode="root_only",
        )
        ledger = {
            "version": 1,
            "phase": "planning",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                row,
                assignment("R-02", "adversarial"),
                assignment("R-03", "measurement_gap"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertTrue(any("root_only rows cannot" in error for error in errors))

    def test_private_plane_cannot_use_prompt_only_public(self) -> None:
        ledger = {
            "version": 1,
            "phase": "planning",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                assignment(
                    "R-01", "primary", source_plane="connector_private"
                ),
                assignment("R-02", "adversarial"),
                assignment("R-03", "measurement_gap"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertTrue(any("must remain root_only" in error for error in errors))
        self.assertTrue(any("allowed only" in error for error in errors))

    def test_accepted_prompt_only_requires_matching_safety(self) -> None:
        accepted = assignment(
            "R-01",
            "primary",
            status="completed",
            acceptance="accepted",
            runtime_verified=True,
            thread_uuid=str(uuid.uuid4()),
            safety_enforcement="unknown",
        )
        ledger = {
            "version": 1,
            "phase": "planning",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                accepted,
                assignment("R-02", "adversarial"),
                assignment("R-03", "measurement_gap"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertTrue(any("requires safety_enforcement=prompt_only" in error for error in errors))

    def test_rejected_unfinished_row_is_invalid(self) -> None:
        row = assignment("R-01", "primary", acceptance="rejected")
        ledger = {
            "version": 1,
            "phase": "planning",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                row,
                assignment("R-02", "adversarial"),
                assignment("R-03", "measurement_gap"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_research_ledger(path)
        self.assertTrue(any("requires acceptance_status=pending" in error for error in errors))

    def test_accepted_ledger_row_reopens_exact_runtime_receipt(self) -> None:
        thread_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        parent_id = str(uuid.uuid4())
        accepted = assignment(
            "R-01",
            "primary",
            status="completed",
            acceptance="accepted",
            runtime_verified=True,
            thread_uuid=thread_id,
        )
        accepted["runtime_turn"] = turn_id
        accepted["parent_thread_uuid"] = parent_id
        ledger = {
            "version": 1,
            "phase": "synthesis",
            "N": 3,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "assignments": [
                accepted,
                assignment(
                    "R-02",
                    "adversarial",
                    status="failed",
                    acceptance="excluded",
                    gap_reason="No independent source.",
                ),
                assignment(
                    "R-03",
                    "measurement_gap",
                    status="failed",
                    acceptance="excluded",
                    gap_reason="No measurement source.",
                ),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            codex_home = Path(temp)
            rollout = codex_home / "sessions" / "x" / f"rollout-{thread_id}.jsonl"
            rollout.parent.mkdir(parents=True)
            write_jsonl(
                rollout,
                rollout_records(thread_id, turn_id, parent_id=parent_id),
            )
            parent_rollout = (
                codex_home / "sessions" / "x" / f"rollout-{parent_id}.jsonl"
            )
            write_jsonl(
                parent_rollout,
                [
                    {"type": "session_meta", "payload": {"id": parent_id}},
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "spawn_agent",
                            "call_id": "call-test",
                            "arguments": json.dumps(
                                {
                                    "task_name": "test_assignment",
                                    "message": "bounded task",
                                    "agent_type": "default",
                                    "fork_turns": "none",
                                }
                            ),
                        },
                    },
                ],
            )
            ledger_path = codex_home / "ledger.json"
            write_json(ledger_path, ledger)
            static_errors, _ = CHECK.validate_research_ledger(ledger_path)
            receipt_errors, _ = CHECK.validate_ledger_receipts(
                ledger_path, codex_home
            )
        self.assertEqual(static_errors, [])
        self.assertEqual(receipt_errors, [])


class ProjectLedgerTests(unittest.TestCase):
    def test_project_planning_ledger_passes(self) -> None:
        ledger = {
            "ledger_type": "project",
            "version": 1,
            "phase": "planning",
            "closure_status": "open",
            "root_integration_status": "not_started",
            "root_integration_receipt": None,
            "N": 2,
            "verifier_reserve": 1,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "target_gate": "LOCAL_PASS",
            "verified_gates": [],
            "gate_receipts": {},
            "external_authority": False,
            "assignments": [
                project_assignment("P-01", "builder", ownership=["src/a.py"]),
                project_assignment("P-02", "verifier"),
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project-ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_assignment_ledger(path)
        self.assertEqual(errors, [])

    def test_complete_project_requires_integrated_builder_and_verifier(self) -> None:
        builder = project_assignment(
            "P-01",
            "builder",
            status="completed",
            acceptance="accepted",
            ownership=["src/a.py"],
            integration_status="pending",
        )
        verifier = project_assignment(
            "P-02",
            "verifier",
            status="completed",
            acceptance="rejected",
            dependencies=["P-01"],
        )
        ledger = {
            "ledger_type": "project",
            "version": 1,
            "phase": "closure",
            "closure_status": "complete",
            "root_integration_status": "completed",
            "root_integration_receipt": "receipt:integration",
            "N": 2,
            "verifier_reserve": 1,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "target_gate": "LOCAL_PASS",
            "verified_gates": ["LOCAL_PASS"],
            "gate_receipts": {"LOCAL_PASS": "receipt:local"},
            "external_authority": False,
            "assignments": [builder, verifier],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project-ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_project_ledger(path)
        self.assertTrue(any("must be integrated" in error for error in errors))
        self.assertTrue(any("accepted verifier" in error for error in errors))

    def test_project_rejects_overlapping_builder_ownership(self) -> None:
        first = project_assignment(
            "P-01",
            "builder",
            status="completed",
            acceptance="accepted",
            ownership=["src/shared.py"],
            integration_status="integrated",
        )
        second = project_assignment(
            "P-02",
            "builder",
            status="completed",
            acceptance="accepted",
            ownership=["src/shared.py"],
            integration_status="integrated",
        )
        verifier = project_assignment("P-03", "verifier")
        ledger = {
            "ledger_type": "project",
            "version": 1,
            "phase": "integration",
            "closure_status": "open",
            "root_integration_status": "in_progress",
            "root_integration_receipt": None,
            "N": 3,
            "verifier_reserve": 1,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "target_gate": "LOCAL_PASS",
            "verified_gates": [],
            "gate_receipts": {},
            "external_authority": False,
            "assignments": [first, second, verifier],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project-ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_project_ledger(path)
        self.assertTrue(any("ownership" in error for error in errors))

    def test_external_gate_requires_authority_and_contiguous_receipts(self) -> None:
        ledger = {
            "ledger_type": "project",
            "version": 1,
            "phase": "planning",
            "closure_status": "open",
            "root_integration_status": "not_started",
            "root_integration_receipt": None,
            "N": 1,
            "verifier_reserve": 1,
            "overall_deadline": "2026-08-16T12:00:00+09:00",
            "target_gate": "PROVIDER_PASS",
            "verified_gates": ["LOCAL_PASS", "PROVIDER_PASS"],
            "gate_receipts": {"LOCAL_PASS": "receipt:local"},
            "external_authority": False,
            "assignments": [project_assignment("P-01", "verifier")],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project-ledger.json"
            write_json(path, ledger)
            errors, _ = CHECK.validate_project_ledger(path)
        self.assertTrue(any("contiguous prefix" in error for error in errors))
        self.assertTrue(any("external_authority=true" in error for error in errors))


class TreeV2Tests(unittest.TestCase):
    def _ledger(self, rows, **overrides):
        value = {
            "version": 2, "tree_id": str(uuid.uuid4()), "run_id": str(uuid.uuid4()),
            "attempt_budget_N": len(rows), "concurrency_cap_C": 2,
            "wave_width_W": 2, "max_workflow_depth": 2, "verifier_reserve_V": 1,
            "phase": "planning", "closure_status": "open",
            "overall_deadline": "2026-01-01T01:00:00Z",
            "assignments": rows,
        }
        value.update(overrides)
        return value

    def _valid_rows(self):
        root_parent = str(uuid.uuid4())
        coordinator_thread = str(uuid.uuid4())
        return [
            {"attempt_id": "c", "parent_attempt_id": None, "depth": 1, "wave": 1,
             "root_parent_thread_uuid": root_parent, "root_parent_call_id": "root-call",
             "delegated_by": {"parent_thread_uuid": root_parent, "parent_call_id": "root-call"},
             "role": "coordinator", "may_spawn_descendants": True,
             "descendant_budget": 3, "planned_child_attempt_ids": ["l1", "l2", "l3"],
             "collected_result_ids": ["l1", "l2", "l3"], "execution_status": "completed",
             "acceptance_status": "accepted", "runtime_verified": True, "thread_uuid": coordinator_thread, "runtime_turn": str(uuid.uuid4()), "collection_receipt": "receipt:c",
             "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:04:00Z"},
            {"attempt_id": "l1", "parent_attempt_id": "c", "depth": 2, "wave": 2,
             "delegated_by": {"parent_attempt_id": "c", "parent_thread_uuid": coordinator_thread, "parent_call_id": "call-1"},
             "role": "research_scout_luna", "may_spawn_descendants": False,
             "kind": "evidence_lane", "coverage_cell": "primary", "priority": False,
             "quota_label": "primary", "source_plane": "public_web", "access_mode": "prompt_only_public",
             "source_universe": "official", "exclusion_rule": "no mirrors", "overlap_key": "primary",
             "deadline": "2026-01-01T00:30:00Z", "runtime_verified": False, "safety_enforcement": "unknown",
             "execution_status": "completed", "acceptance_status": "rejected", "started_at": "2026-01-01T00:01:00Z", "finished_at": "2026-01-01T00:02:00Z"},
            {"attempt_id": "l2", "parent_attempt_id": "c", "depth": 2, "wave": 2,
             "delegated_by": {"parent_attempt_id": "c", "parent_thread_uuid": coordinator_thread, "parent_call_id": "call-2"},
             "role": "leaf", "kind": "contradiction", "may_spawn_descendants": False,
             "coverage_cell": "adversarial", "priority": False, "quota_label": "adversarial",
             "source_plane": "public_web", "access_mode": "prompt_only_public",
             "source_universe": "contrary", "exclusion_rule": "no mirrors", "overlap_key": "adversarial",
             "deadline": "2026-01-01T00:30:00Z", "runtime_verified": False, "safety_enforcement": "unknown",
             "execution_status": "completed", "acceptance_status": "rejected", "started_at": "2026-01-01T00:02:00Z", "finished_at": "2026-01-01T00:03:00Z"},
            {"attempt_id": "l3", "parent_attempt_id": "c", "depth": 2, "wave": 3,
             "delegated_by": {"parent_attempt_id": "c", "parent_thread_uuid": coordinator_thread, "parent_call_id": "call-3"},
             "role": "research_scout_luna", "kind": "evidence_lane", "may_spawn_descendants": False,
             "coverage_cell": "measurement", "priority": False, "quota_label": "measurement_gap",
             "source_plane": "public_web", "access_mode": "prompt_only_public",
             "source_universe": "data", "exclusion_rule": "no commentary", "overlap_key": "measurement",
             "deadline": "2026-01-01T00:30:00Z", "runtime_verified": False, "safety_enforcement": "unknown",
             "execution_status": "completed", "acceptance_status": "rejected", "started_at": "2026-01-01T00:03:00Z", "finished_at": "2026-01-01T00:04:00Z"},
        ]

    def test_tree_v2_valid(self):
        errors, _ = CHECK._validate_tree_ledger(self._ledger(self._valid_rows()))
        self.assertEqual(errors, [])

    def test_tree_v2_rejects_depth_cycle_and_budget(self):
        rows = self._valid_rows(); rows[2]["parent_attempt_id"] = "l2"; rows[2]["depth"] = 3
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows, attempt_budget_N=1))
        self.assertTrue(any("depth" in e or "cycle" in e or "budget" in e for e in errors))

    def test_tree_v2_rejects_leaf_spawn_and_unlisted_child(self):
        rows = self._valid_rows(); rows[1]["hidden_spawn"] = True; rows[0]["planned_child_attempt_ids"] = ["l1"]
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows))
        self.assertTrue(any("leaf rollout" in e for e in errors))
        self.assertTrue(any("planned child list" in e for e in errors))

    def test_tree_v2_rejects_accepted_completion_after_assignment_deadline(self):
        rows = self._valid_rows()
        rows[0]["finished_at"] = "2026-01-01T00:40:00Z"
        rows[1].update({
            "acceptance_status": "accepted",
            "runtime_verified": True,
            "thread_uuid": str(uuid.uuid4()),
            "runtime_turn": str(uuid.uuid4()),
            "safety_enforcement": "prompt_only",
            "finished_at": "2026-01-01T00:31:00Z",
        })
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows))
        self.assertTrue(any("accepted completion exceeds assignment deadline" in e for e in errors))

    def test_tree_v2_rejects_start_after_overall_deadline(self):
        rows = self._valid_rows()
        errors, _ = CHECK._validate_tree_ledger(
            self._ledger(rows, overall_deadline="2025-12-31T23:59:00Z")
        )
        self.assertTrue(any("started_at exceeds overall_deadline" in e for e in errors))

    def test_root_only_gap_can_close_without_child_dispatch(self):
        rows = self._valid_rows()
        rows[1].update({
            "source_plane": "connector_private",
            "access_mode": "root_only",
            "execution_status": "not_dispatched",
            "acceptance_status": "excluded",
            "runtime_verified": False,
            "thread_uuid": None,
            "runtime_turn": None,
            "started_at": None,
            "finished_at": "2026-01-01T00:01:30Z",
            "priority": True,
            "gap_reason": "private connector access remains root-only",
        })
        errors, _ = CHECK._validate_tree_ledger(
            self._ledger(rows, phase="synthesis", closure_status="blocked")
        )
        self.assertEqual(errors, [])

    def test_root_only_terminal_requires_explicit_gap_reason(self):
        rows = self._valid_rows()
        rows[1].update({
            "source_plane": "connector_private",
            "access_mode": "root_only",
            "execution_status": "not_dispatched",
            "acceptance_status": "excluded",
            "runtime_verified": False,
            "thread_uuid": None,
            "runtime_turn": None,
            "started_at": None,
            "finished_at": "2026-01-01T00:01:30Z",
            "gap_reason": None,
        })
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows))
        self.assertTrue(any("requires a non-empty gap_reason" in error for error in errors))

    def test_incomplete_child_returns_errors_instead_of_crashing_coordinator_check(self):
        rows = self._valid_rows()
        rows[1].update({
            "execution_status": "started",
            "acceptance_status": "pending",
            "finished_at": None,
        })
        errors, _ = CHECK._validate_tree_ledger(
            self._ledger(rows, phase="synthesis", closure_status="blocked")
        )
        self.assertTrue(any("child is not terminal" in error for error in errors))
        self.assertTrue(any("planned/started attempts" in error for error in errors))

    def test_root_only_without_terminal_timestamp_returns_structured_error(self):
        rows = self._valid_rows()
        rows[1].update({
            "source_plane": "provider",
            "access_mode": "root_only",
            "execution_status": "not_dispatched",
            "acceptance_status": "excluded",
            "runtime_verified": False,
            "thread_uuid": None,
            "runtime_turn": None,
            "started_at": None,
            "finished_at": None,
            "gap_reason": "provider access remains root-only",
        })
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows))
        self.assertTrue(any("terminal row requires" in error for error in errors))


class V5FailureInjectionTests(unittest.TestCase):
    def base(self, **kw):
        root_thread = str(uuid.uuid4())
        def research_row(attempt_id, call_id, quota, coverage, role, kind, wave):
            return {"attempt_id":attempt_id, "parent_attempt_id":None, "depth":1,
                    "root_parent_thread_uuid":root_thread, "root_parent_call_id":call_id,
                    "delegated_by":{"parent_thread_uuid":root_thread,"parent_call_id":call_id},
                    "role":role, "kind":kind, "wave":wave, "execution_status":"planned", "acceptance_status":"pending",
                    "coverage_cell":coverage, "priority":False, "quota_label":quota,
                    "source_plane":"public_web", "access_mode":"prompt_only_public", "safety_enforcement":"unknown",
                    "source_universe":coverage + " universe", "exclusion_rule":"exclude mirrors", "overlap_key":coverage,
                    "deadline":"2026-01-01T00:30:00Z", "runtime_verified":False}
        row = research_row("a", "c-a", "primary", "primary", "verifier", "verifier", 1)
        rows = [
            row,
            research_row("q-adversarial", "c-b", "adversarial", "adversarial", "research_scout_luna", "contradiction", 1),
            research_row("q-measurement", "c-c", "measurement_gap", "measurement", "research_scout_luna", "evidence_lane", 2),
        ]
        ledger_kw = {k: kw.pop(k) for k in list(kw) if k in {"phase", "closure_status", "verifier_reserve_V", "concurrency_cap_C", "wave_width_W", "attempt_budget_N"}}
        row.update(kw); value = {"version":2,"tree_id":str(uuid.uuid4()),"run_id":str(uuid.uuid4()),"attempt_budget_N":4,"concurrency_cap_C":2,"wave_width_W":2,"max_workflow_depth":2,"verifier_reserve_V":1,"phase":"planning","closure_status":"open","overall_deadline":"2026-01-01T01:00:00Z","assignments":rows}; value.update(ledger_kw); return value
    def check(self, ledger): return CHECK._validate_tree_ledger(ledger)
    def test_reserve_zero_for_large_n(self): self.assertTrue(self.check(self.base(verifier_reserve_V=0))[0])
    def test_reserve_equal_n(self): self.assertTrue(self.check(self.base(verifier_reserve_V=4))[0])
    def test_reserve_uses_fifteen_percent_ceiling(self):
        errors, _ = self.check(self.base(attempt_budget_N=20, verifier_reserve_V=1))
        self.assertTrue(any("ceil(.15*N)" in error for error in errors))
    def test_reserve_must_equal_policy_not_exceed_it(self):
        errors, _ = self.check(self.base(attempt_budget_N=8, verifier_reserve_V=3))
        self.assertTrue(any("must equal" in error for error in errors))
    def test_planned_rows_count_toward_global_budget(self):
        ledger = self.base()
        template = ledger["assignments"][-1]
        for index in range(2):
            call = f"planned-budget-{index}"
            thread = str(uuid.uuid4())
            ledger["assignments"].append(dict(
                template,
                attempt_id=f"planned-{index}",
                root_parent_thread_uuid=thread,
                root_parent_call_id=call,
                delegated_by={"parent_thread_uuid": thread, "parent_call_id": call},
                coverage_cell=f"planned-{index}",
                source_universe=f"planned-universe-{index}",
                overlap_key=f"planned-{index}",
            ))
        self.assertTrue(any("plans" in error and "attempt_budget_N" in error for error in self.check(ledger)[0]))
    def test_planned_rows_count_toward_wave_width(self):
        ledger = self.base(wave_width_W=1)
        self.assertTrue(any("plans/starts" in error for error in self.check(ledger)[0]))
    def test_planned_nonreserve_rows_cannot_spend_reserve(self):
        ledger = self.base()
        for reserve in ledger["assignments"][:2]:
            reserve["role"] = "research_scout_luna"
            reserve["kind"] = "evidence_lane"
        template = ledger["assignments"][-1]
        ledger["assignments"].append(dict(
            template,
            attempt_id="planned-reserve-intrusion",
            wave=3,
            quota="other",
            perspective="other",
            coverage_cell="planned-reserve-intrusion",
            source_universe="planned reserve intrusion universe",
            overlap_key="planned-reserve-intrusion",
        ))
        self.assertTrue(any("non-reserve attempts" in error for error in self.check(ledger)[0]))
    def test_wave_width_must_fit_cap_and_budget(self):
        errors, _ = self.check(self.base(wave_width_W=3, concurrency_cap_C=2))
        self.assertTrue(any("wave_width_W" in error and "cap" in error for error in errors))
        errors, _ = self.check(self.base(wave_width_W=5, attempt_budget_N=4))
        self.assertTrue(any("wave_width_W" in error and "budget" in error for error in errors))
    def test_wave_start_count_cannot_exceed_width(self):
        ledger = self.base(wave_width_W=1)
        first = ledger["assignments"][0]
        for index in range(2):
            call = f"call-{index}"
            thread = str(uuid.uuid4())
            ledger["assignments"].append({
                "attempt_id": f"b{index}", "parent_attempt_id": None,
                "depth": 1, "wave": 2,
                "root_parent_thread_uuid": thread, "root_parent_call_id": call,
                "delegated_by": {"parent_thread_uuid": thread, "parent_call_id": call},
                "role": "builder", "execution_status": "completed",
                "acceptance_status": "rejected",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:01:00Z",
            })
        self.assertTrue(any("wave 2" in error for error in self.check(ledger)[0]))
    def test_cap_exceeds_config(self): self.assertTrue(any("exceeds configured" in e for e in CHECK._validate_tree_ledger(self.base(concurrency_cap_C=3), configured_cap=2)[0]))
    def test_research_dispatch_passes_configured_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research-v2.json"
            ledger = self.base(concurrency_cap_C=2)
            ledger["assignments"][0]["root_parent_thread_uuid"] = ledger["assignments"][0]["delegated_by"]["parent_thread_uuid"]
            ledger["assignments"][0]["root_parent_call_id"] = ledger["assignments"][0]["delegated_by"]["parent_call_id"]
            path.write_text(json.dumps(ledger), encoding="utf-8")
            errors, warnings = CHECK.validate_assignment_ledger(path, configured_cap=2)
            self.assertFalse(any("configured-cap proof" in warning for warning in warnings))
            self.assertEqual(errors, [])
    def test_cap_unset_warns(self): self.assertTrue(any("live configured-cap" in w for w in self.check(self.base())[1]))
    def test_retry_cell_mismatch(self):
        l=self.base(); l["assignments"].append(dict(l["assignments"][0],attempt_id="b",retry_of="a",cell_id="x")); l["assignments"][0]["cell_id"]="y"; self.assertTrue(any("cell_id" in e for e in self.check(l)[0]))
    def test_retry_owner_mismatch(self):
        l=self.base(owner="x"); l["assignments"].append(dict(l["assignments"][0],attempt_id="b",retry_of="a",owner="y")); self.assertTrue(any("owner" in e for e in self.check(l)[0]))
    def test_retry_ordinal_gap(self):
        l=self.base(attempt_ordinal=1); l["assignments"].append(dict(l["assignments"][0],attempt_id="b",retry_of="a",attempt_ordinal=3)); self.assertTrue(any("consecutive" in e for e in self.check(l)[0]))
    def test_duplicate_planned_children(self):
        l=self.base(role="coordinator",depth=1,planned_child_attempt_ids=["x","x"],collected_result_ids=[]); self.assertTrue(any("duplicates" in e for e in self.check(l)[0]))
    def test_role_kind_mismatch(self):
        l=self.base(kind="builder",role="verifier"); self.assertTrue(self.check(l)[0])
    def test_phase_closure_reserve_gap(self):
        l=self.base(phase="closure",closure_status="open"); self.assertTrue(any("closure requires" in e for e in self.check(l)[0]))
    def test_complete_requires_reserve(self):
        l=self.base(phase="closure",closure_status="complete"); self.assertTrue(any("complete closure" in e for e in self.check(l)[0]))
    def test_nonreserve_erosion(self):
        l=self.base(); l["assignments"][0]["role"]="builder"; l["assignments"][0]["kind"]="builder"; l["assignments"] += [dict(l["assignments"][0],attempt_id=str(i),parent_attempt_id=None) for i in range(4)]; self.assertTrue(self.check(l)[0])
    def test_late_timeout_rejected(self):
        l=self.base(execution_status="timed_out",acceptance_status="accepted",started_at="2026-01-01T00:00:00Z",finished_at="2026-01-01T00:01:00Z"); self.assertTrue(any("state transition" in e or "late completion" in e for e in self.check(l)[0]))

    def test_direct_root_children_count_toward_concurrency(self):
        ledger = self.base(concurrency_cap_C=1)
        root_thread = str(uuid.uuid4())
        rows = []
        for attempt_id, call_id in (("b1", "call-1"), ("b2", "call-2")):
            rows.append({
                "attempt_id": attempt_id,
                "parent_attempt_id": None,
                "depth": 1,
                "root_parent_thread_uuid": root_thread,
                "root_parent_call_id": call_id,
                "delegated_by": {"parent_thread_uuid": root_thread, "parent_call_id": call_id},
                "role": "builder",
                "kind": "evidence_lane",
                "wave": 1,
                "coverage_cell": f"concurrency-{attempt_id}",
                "priority": False,
                "quota_label": "other",
                "source_plane": "public_web",
                "access_mode": "prompt_only_public",
                "safety_enforcement": "unknown",
                "source_universe": f"universe-{attempt_id}",
                "exclusion_rule": "exclude mirrors",
                "overlap_key": f"concurrency-{attempt_id}",
                "deadline": "2026-01-01T00:30:00Z",
                "runtime_verified": False,
                "execution_status": "started",
                "acceptance_status": "pending",
                "started_at": "2026-01-01T00:00:00Z",
            })
        ledger["assignments"].extend(rows)
        self.assertTrue(any("concurrency cap" in error for error in self.check(ledger)[0]))

    def test_research_complete_rejects_live_started_attempt(self):
        ledger = self.base(phase="synthesis", closure_status="complete")
        row = ledger["assignments"][0]
        row.update({
            "execution_status": "started",
            "acceptance_status": "pending",
            "started_at": "2026-01-01T00:00:00Z",
        })
        self.assertTrue(any("synthesis cannot contain" in error for error in self.check(ledger)[0]))

    def test_research_v2_enforces_perspective_quotas(self):
        ledger = self.base()
        for row in ledger["assignments"]:
            row["quota_label"] = "other"
        errors, _ = self.check(ledger)
        self.assertTrue(any("unique primary" in error for error in errors))
        self.assertTrue(any("unique adversarial" in error for error in errors))
        self.assertTrue(any("measurement_gap" in error for error in errors))

    def test_research_v2_rejects_duplicate_coverage_cell(self):
        ledger = self.base()
        ledger["assignments"][1]["coverage_cell"] = ledger["assignments"][0]["coverage_cell"]
        self.assertTrue(any("coverage_cell" in error and "duplicated" in error for error in self.check(ledger)[0]))

    def test_research_v2_rejects_invalid_source_plane(self):
        ledger = self.base()
        ledger["assignments"][0]["source_plane"] = "invented"
        self.assertTrue(any("source_plane" in error for error in self.check(ledger)[0]))

    def test_research_v2_priority_requires_acceptance_or_gap(self):
        ledger = self.base(phase="synthesis", closure_status="blocked")
        for index, row in enumerate(ledger["assignments"]):
            row["execution_status"] = "completed"
            row["acceptance_status"] = "rejected"
            row["started_at"] = f"2026-01-01T00:0{index}:00Z"
            row["finished_at"] = f"2026-01-01T00:1{index}:00Z"
        ledger["assignments"][0]["priority"] = True
        self.assertTrue(any("priority cell" in error for error in self.check(ledger)[0]))

    def test_duplicate_delegated_edge_is_rejected(self):
        ledger = self.base()
        first = ledger["assignments"][0]
        first["root_parent_thread_uuid"] = first["delegated_by"]["parent_thread_uuid"]
        first["root_parent_call_id"] = first["delegated_by"]["parent_call_id"]
        duplicate = dict(first, attempt_id="duplicate")
        ledger["assignments"].append(duplicate)
        self.assertTrue(any("delegated edge" in error for error in self.check(ledger)[0]))

    def test_retry_chain_respects_global_limit(self):
        ledger = self.base(retry_owner="root", cell_id="cell", attempt_ordinal=1)
        first = ledger["assignments"][0]
        second = dict(first, attempt_id="b", retry_of="a", attempt_ordinal=2)
        third = dict(first, attempt_id="c", retry_of="b", attempt_ordinal=3)
        ledger["assignments"].extend([second, third])
        self.assertTrue(any("retry_limit" in error for error in self.check(ledger)[0]))

    def test_project_v2_complete_requires_root_integration_and_target_gate(self):
        ledger = {
            "ledger_type": "project",
            "version": 2,
            "phase": "closure",
            "closure_status": "complete",
            "overall_deadline": "2026-01-01T01:00:00Z",
            "root_integration_status": "not_started",
            "root_integration_receipt": None,
            "target_gate": "LOCAL_PASS",
            "verified_gates": [],
            "gate_receipts": {},
            "external_authority": False,
            "assignments": [],
        }
        errors = CHECK._validate_project_v2_contract(ledger)
        self.assertTrue(any("root integration" in error for error in errors))
        self.assertTrue(any("target_gate" in error for error in errors))

    def test_project_v2_rejects_start_before_dependency_finishes(self):
        root_thread = str(uuid.uuid4())
        rows = [
            {
                "attempt_id": "builder",
                "parent_attempt_id": None,
                "depth": 1,
                "root_parent_thread_uuid": root_thread,
                "root_parent_call_id": "call-builder",
                "delegated_by": {
                    "parent_thread_uuid": root_thread,
                    "parent_call_id": "call-builder",
                },
                "kind": "builder",
                "role": "default",
                "dependencies": [],
                "may_spawn_descendants": False,
                "execution_status": "completed",
                "acceptance_status": "rejected",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:10:00Z",
            },
            {
                "attempt_id": "reviewer",
                "parent_attempt_id": None,
                "depth": 1,
                "root_parent_thread_uuid": root_thread,
                "root_parent_call_id": "call-reviewer",
                "delegated_by": {
                    "parent_thread_uuid": root_thread,
                    "parent_call_id": "call-reviewer",
                },
                "kind": "reviewer",
                "role": "reviewer",
                "dependencies": ["builder"],
                "may_spawn_descendants": False,
                "execution_status": "completed",
                "acceptance_status": "rejected",
                "started_at": "2026-01-01T00:05:00Z",
                "finished_at": "2026-01-01T00:15:00Z",
            },
        ]
        ledger = {
            "version": 2,
            "tree_id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "attempt_budget_N": 4,
            "concurrency_cap_C": 2,
            "wave_width_W": 2,
            "max_workflow_depth": 2,
            "verifier_reserve_V": 1,
            "assignments": rows,
        }
        errors, _ = CHECK._validate_tree_ledger(ledger, project=True)
        self.assertTrue(any("started before dependency" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
