from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
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
                "effort": "max",
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
        "runtime_effort": "max" if accepted else None,
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
        "runtime_effort": "max" if accepted else None,
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

    def test_validator_accepts_optional_message_property(self) -> None:
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
            errors, warnings = CHECK.validate_spawn_schema(path, "default")
        self.assertEqual(errors, [])
        self.assertTrue(any("message is optional" in warning for warning in warnings))

    def test_validator_rejects_missing_message_property(self) -> None:
        document = {
            "name": "spawn_agent",
            "parameters": {
                "properties": {
                    "agent_type": {"enum": ["default"]},
                    "fork_turns": {"enum": ["none"]},
                },
                "required": ["agent_type", "fork_turns"],
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
    def test_accepted_runtime_metadata_rejects_truthy_non_boolean_and_non_string_uuid(self) -> None:
        row = {
            "runtime_verified": 1,
            "thread_uuid": uuid.uuid4(),
            "runtime_turn": str(uuid.uuid4()),
            "parent_thread_uuid": str(uuid.uuid4()),
            "runtime_model": "gpt-5.6-luna",
            "runtime_effort": "max",
            "agent_role": "default",
            "spawn_kind": "spawn_agent",
            "parent_call_id": "call-1",
            "safety_enforcement": "prompt_only",
        }
        errors = CHECK._accepted_runtime_errors("row", row)
        self.assertTrue(any("runtime_verified=true" in error for error in errors))
        self.assertTrue(any("thread_uuid UUID" in error for error in errors))

    def test_generic_worker_policy_is_explicit_and_fail_closed(self) -> None:
        errors, _ = CHECK.validate_role_policy({}, [], "worker")
        self.assertTrue(any("allow-generic-worker" in error for error in errors))
        errors, _ = CHECK.validate_role_policy({}, [], "worker", True)
        self.assertEqual(errors, [])

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
                        "effort": "max",
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
                            "effort": "max",
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

    def test_runtime_requires_parent_depth_and_role(self) -> None:
        records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        spawn = records[0]["payload"]["source"]["subagent"]["thread_spawn"]
        spawn.pop("agent_path")
        spawn["depth"] = 0
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(path, records)
            errors, _ = CHECK.validate_runtime_rollout(path, "default")
        self.assertTrue(any("depth" in error for error in errors))

    def test_runtime_allows_missing_agent_path_with_warning(self) -> None:
        records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        spawn = records[0]["payload"]["source"]["subagent"]["thread_spawn"]
        spawn.pop("agent_path")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            write_jsonl(path, records)
            errors, warnings = CHECK.validate_runtime_rollout(path, "default")
        self.assertEqual(errors, [])
        self.assertTrue(any("agent_path is unavailable" in warning for warning in warnings))

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
        child_id = child_meta["id"]
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
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-test",
                    "output": json.dumps({"agent_id": child_id}),
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

    def test_parent_task_name_without_returned_child_uuid_is_rejected(self) -> None:
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
                    "arguments": json.dumps({
                        "task_name": "test_assignment",
                        "message": "bounded task",
                        "agent_type": "default",
                        "fork_turns": "none",
                    }),
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent_path = Path(temp) / "parent.jsonl"
            child_path = Path(temp) / "child.jsonl"
            write_jsonl(parent_path, parent_records)
            write_jsonl(child_path, child_records)
            errors, _ = CHECK.validate_spawn_provenance(parent_path, child_path, "default")
        self.assertTrue(any("child_id" in error for error in errors))

    def test_parent_subagent_activity_binds_child_uuid(self) -> None:
        child_records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        child_meta = child_records[0]["payload"]
        child_id = child_meta["id"]
        parent_records = [
            {"type": "session_meta", "payload": {"id": child_meta["parent_thread_id"]}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "call-test",
                    "arguments": json.dumps({
                        "task_name": "test_assignment",
                        "message": "bounded task",
                        "agent_type": "default",
                        "fork_turns": "none",
                    }),
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "SubAgentActivity",
                        "id": "call-test",
                        "kind": "started",
                        "agent_thread_id": child_id,
                    },
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-test",
                    "output": json.dumps({"task_name": "/root/test_assignment"}),
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent_path = Path(temp) / "parent.jsonl"
            child_path = Path(temp) / "child.jsonl"
            write_jsonl(parent_path, parent_records)
            write_jsonl(child_path, child_records)
            errors, _ = CHECK.validate_spawn_provenance(parent_path, child_path, "default")
        self.assertEqual(errors, [])

    def test_nested_exec_spawn_request_is_bound_to_child_uuid(self) -> None:
        child_records = rollout_records(
            str(uuid.uuid4()), str(uuid.uuid4()), role="luna_reviewer"
        )
        child_meta = child_records[0]["payload"]
        child_meta["source"]["subagent"]["thread_spawn"].pop("agent_path")
        parent_id = child_meta["parent_thread_id"]
        child_id = child_meta["id"]
        call_id = "call-nested"
        parent_records = [
            {"type": "session_meta", "payload": {"id": parent_id}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": call_id,
                    "input": (
                        "const r = await tools.multi_agent_v1__spawn_agent({\n"
                        '  agent_type: "luna_reviewer",\n'
                        "  fork_context: false,\n"
                        "  message: `bounded task`,\n"
                        "});\ntext(r);"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": call_id,
                    "output": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {"agent_id": child_id, "nickname": "Adversarial Lens"}
                            ),
                        }
                    ],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent_path = Path(temp) / "parent.jsonl"
            child_path = Path(temp) / "child.jsonl"
            write_jsonl(parent_path, parent_records)
            write_jsonl(child_path, child_records)
            errors, _ = CHECK.validate_spawn_provenance(
                parent_path, child_path, "luna_reviewer"
            )
        self.assertEqual(errors, [])

    def test_parent_full_history_spawn_is_rejected(self) -> None:
        child_records = rollout_records(str(uuid.uuid4()), str(uuid.uuid4()))
        child_meta = child_records[0]["payload"]
        child_id = child_meta["id"]
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
                            "agent_type": "default",
                            "fork_turns": "all",
                        }
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-test",
                    "output": json.dumps({"agent_id": child_id}),
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
        child_id = child_meta["id"]
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
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-test",
                    "output": json.dumps({"agent_id": child_id}),
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
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "call_id": "call-test",
                            "output": json.dumps({"agent_id": thread_id}),
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


class WorkerLedgerIntegrationTests(unittest.TestCase):
    def _run(self, *, opt_in=True, explicit_model="gpt-5.6-luna"):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "codex-home"
            sessions = home / "sessions" / "test"
            sessions.mkdir(parents=True)
            workspace = Path(temp) / "workspace"
            workspace.mkdir()
            (home / "config.toml").write_text(
                "[agents]\nenabled = true\nmax_concurrent_threads_per_session = 4\n",
                encoding="utf-8")
            child, parent, turn = (str(uuid.uuid4()) for _ in range(3))
            write_jsonl(sessions / f"rollout-{child}.jsonl",
                        rollout_records(child, turn, role="worker", parent_id=parent))
            arguments = {"task_name":"test_assignment", "message":"public source cell",
                         "agent_type":"worker", "fork_turns":"none",
                         "reasoning_effort":"max"}
            if explicit_model is not None:
                arguments["model"] = explicit_model
            write_jsonl(sessions / f"rollout-{parent}.jsonl", [
                {"type":"session_meta", "payload":{"id":parent}},
                {"type":"response_item", "payload":{"type":"function_call", "name":"spawn_agent",
                 "call_id":"call-test", "arguments":json.dumps(arguments)}},
                {"type":"response_item", "payload":{"type":"function_call_output", "call_id":"call-test",
                 "output":json.dumps({"agent_id":child})}},
            ])
            row = assignment("R-01", "primary", status="completed", acceptance="accepted",
                             runtime_verified=True, thread_uuid=child)
            row.update(runtime_turn=turn, parent_thread_uuid=parent, agent_role="worker")
            ledger = {"version":1, "phase":"synthesis", "N":3,
                      "overall_deadline":"2026-08-16T12:00:00+09:00", "assignments":[row,
                assignment("R-02", "adversarial", status="failed", acceptance="excluded", gap_reason="No source"),
                assignment("R-03", "measurement_gap", status="failed", acceptance="excluded", gap_reason="No data")]}
            ledger_path=Path(temp)/"ledger.json"
            write_json(ledger_path,ledger)
            argv=["--codex-home",str(home),"--workspace",str(workspace),"--agent-role","worker",
                  "--ledger-json",str(ledger_path),"--verify-ledger-receipts"]
            if opt_in:argv.append("--allow-generic-worker")
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=CHECK.main(argv)
            return code,output.getvalue()

    def test_worker_opt_in_reaches_final_ledger_verification(self):
        code,output=self._run()
        self.assertEqual(code,0,output)
        self.assertIn("accepted runtime receipts passed revalidation",output)
        self.assertNotIn("NEXT: verify a completed probe",output)

    def test_worker_final_verification_requires_opt_in(self):
        code,output=self._run(opt_in=False)
        self.assertNotEqual(code,0)
        self.assertIn("allow-generic-worker",output)

    def test_worker_final_verification_still_requires_explicit_model(self):
        code,output=self._run(explicit_model=None)
        self.assertNotEqual(code,0)
        self.assertIn("must explicitly set model",output)


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
             "parent_thread_uuid": root_parent, "parent_call_id": "root-call", "agent_role": "coordinator",
             "runtime_model": "gpt-5.6-luna", "runtime_effort": "max", "spawn_kind": "spawn_agent", "safety_enforcement": "prompt_only",
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

    def test_tree_v2_requires_explicit_acceptance_status(self):
        rows = self._valid_rows()
        rows[1].pop("acceptance_status")
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows))
        self.assertTrue(any("acceptance_status is required" in error for error in errors))

    def test_tree_v2_accepted_requires_full_runtime_fields(self):
        rows = self._valid_rows()
        rows[0].pop("parent_call_id")
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows))
        self.assertTrue(any("parent_call_id" in error for error in errors))

    def test_tree_v2_rejects_nested_phase_conflict(self):
        ledger = self._ledger(self._valid_rows(), phase="integration")
        ledger["tree"] = dict(ledger)
        ledger["tree"]["phase"] = "planning"
        errors, _ = CHECK._validate_tree_ledger(ledger, project=True)
        self.assertTrue(any("phase conflicts" in error for error in errors))

    def test_planning_rejects_collecting_nonterminal_child(self):
        rows = self._valid_rows()
        rows[0].update({
            "collected_result_ids": ["l1"],
            "execution_status": "started",
            "acceptance_status": "pending",
            "finished_at": None,
        })
        rows[1].update({
            "execution_status": "started",
            "acceptance_status": "pending",
            "finished_at": None,
        })
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows, phase="planning"))
        self.assertTrue(any("collected child is not terminal" in error for error in errors))

    def _same_family_synthesis_rows(self):
        rows = self._valid_rows()
        for row in (rows[1], rows[3]):
            row.update({
                "acceptance_status": "accepted",
                "runtime_verified": True,
                "thread_uuid": str(uuid.uuid4()),
                "runtime_turn": str(uuid.uuid4()),
                "parent_thread_uuid": rows[0]["thread_uuid"],
                "parent_call_id": f"call-{row['attempt_id']}",
                "agent_role": "research_scout_luna",
                "runtime_model": "gpt-5.6-luna",
                "runtime_effort": "max",
                "spawn_kind": "spawn_agent",
                "safety_enforcement": "prompt_only",
                "source_family_id": "same-upstream",
            })
        # A distinct adversarial cell is a terminal, explicit root-only gap.
        rows[2].update(execution_status="not_dispatched", acceptance_status="excluded",
                       started_at=None, access_mode="root_only", gap_reason="No independent authority available")
        return rows

    def test_research_synthesis_accepts_distinct_cells_from_one_family(self):
        rows = self._same_family_synthesis_rows()
        errors, warnings = CHECK._validate_tree_ledger(
            self._ledger(rows, phase="synthesis", closure_status="blocked")
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("one independent source family" in warning for warning in warnings))

    def test_research_synthesis_normalizes_repeated_family(self):
        rows = self._same_family_synthesis_rows()
        rows[3]["source_family_id"] = "  SAME-UPSTREAM  "
        errors, warnings = CHECK._validate_tree_ledger(
            self._ledger(rows, phase="synthesis", closure_status="blocked")
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("one independent source family" in warning for warning in warnings))

    def test_research_synthesis_still_rejects_duplicate_coverage(self):
        rows = self._same_family_synthesis_rows()
        rows[3]["coverage_cell"] = rows[1]["coverage_cell"]
        errors, _ = CHECK._validate_tree_ledger(
            self._ledger(rows, phase="synthesis", closure_status="blocked")
        )
        self.assertTrue(any("coverage_cell" in error and "duplicated" in error for error in errors))

    def test_research_synthesis_still_requires_source_family(self):
        rows = self._same_family_synthesis_rows()
        rows[3]["source_family_id"] = " "
        errors, _ = CHECK._validate_tree_ledger(
            self._ledger(rows, phase="synthesis", closure_status="blocked")
        )
        self.assertTrue(any("source_family_id is required" in error for error in errors))

    def test_project_evidence_lane_enforces_plane_access_pair(self):
        rows = self._valid_rows()
        rows[1].update({
            "source_plane": "provider",
            "access_mode": "prompt_only_public",
        })
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows), project=True)
        self.assertTrue(any("provider" in error and "root_only" in error for error in errors))

    def test_verifier_results_are_typed(self):
        self.assertTrue(CHECK._verifier_result_errors("v", {}))
        row = {
            "criterion_results": [
                {
                    "criterion_id": "routing",
                    "status": "passed",
                    "evidence_locator": "receipt:routing",
                }
            ]
        }
        self.assertEqual(CHECK._verifier_result_errors("v", row), [])

    def test_tree_v2_planning_allows_uncollected_nonterminal_children(self):
        rows = self._valid_rows()
        rows[0].update({
            "collected_result_ids": [],
            "execution_status": "started",
            "acceptance_status": "pending",
            "finished_at": None,
        })
        for child in rows[1:]:
            child.update({
                "execution_status": "planned",
                "acceptance_status": "pending",
                "started_at": None,
                "finished_at": None,
            })
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows, phase="planning"))
        self.assertEqual(errors, [])

    def test_tree_v2_rejects_depth_cycle_and_budget(self):
        rows = self._valid_rows(); rows[2]["parent_attempt_id"] = "l2"; rows[2]["depth"] = 3
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows, attempt_budget_N=1))
        self.assertTrue(any("depth" in e or "cycle" in e or "budget" in e for e in errors))

    def test_tree_v2_rejects_leaf_spawn_and_unlisted_child(self):
        rows = self._valid_rows(); rows[1]["hidden_spawn"] = True; rows[0]["planned_child_attempt_ids"] = ["l1"]
        errors, _ = CHECK._validate_tree_ledger(self._ledger(rows))
        self.assertTrue(any("non-coordinator rollout" in e for e in errors))
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
        for child, reason in zip(
            rows[2:],
            ("no independent adversarial source", "no measurement source"),
        ):
            child.update({
                "execution_status": "not_dispatched",
                "acceptance_status": "excluded",
                "runtime_verified": False,
                "thread_uuid": None,
                "runtime_turn": None,
                "started_at": None,
                "finished_at": "2026-01-01T00:01:30Z",
                "gap_reason": reason,
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



class RecursiveTreeTests(unittest.TestCase):
    _ledger = TreeV2Tests._ledger
    _valid_rows = TreeV2Tests._valid_rows
    def recursive(self, depth=4):
        import copy
        original = self._valid_rows()
        coordinators = []
        for level in range(1, depth):
            row = copy.deepcopy(original[0])
            row.update(attempt_id=f"c{level}", depth=level, wave=level,
                       thread_uuid=str(uuid.uuid4()), agent_role="default",
                       acceptance_status="rejected", runtime_verified=False,
                       descendant_budget=depth-level+2)
            if coordinators:
                parent = coordinators[-1]
                row.update(parent_attempt_id=parent["attempt_id"],
                           parent_thread_uuid=parent["thread_uuid"], parent_call_id=f"call-c{level}")
                row["delegated_by"] = {"parent_attempt_id": parent["attempt_id"],
                    "parent_thread_uuid": parent["thread_uuid"], "parent_call_id": f"call-c{level}"}
                row.pop("root_parent_thread_uuid")
                row.pop("root_parent_call_id")
            row["planned_child_attempt_ids"] = [f"c{level+1}"] if level < depth-1 else ["l1", "l2", "l3"]
            row["collected_result_ids"] = list(row["planned_child_attempt_ids"])
            coordinators.append(row)
        leaves = original[1:]
        for index, row in enumerate(leaves):
            row.update(parent_attempt_id=coordinators[-1]["attempt_id"], depth=depth, wave=depth+index)
            row["delegated_by"].update(parent_attempt_id=coordinators[-1]["attempt_id"], parent_thread_uuid=coordinators[-1]["thread_uuid"])
        return self._ledger(coordinators+leaves, max_workflow_depth=depth,
                            concurrency_cap_C=depth, wave_width_W=2)

    def check_recursive(self, ledger):
        return CHECK._validate_tree_ledger(ledger, project=True)[0]

    def test_recursive_depth_three_and_four(self):
        for depth in (3, 4):
            with self.subTest(depth=depth):
                self.assertEqual(self.check_recursive(self.recursive(depth)), [])

    def test_recursive_research_depth_three(self):
        self.assertEqual(CHECK._validate_tree_ledger(self.recursive(3))[0], [])

    def test_recursive_research_depth_four_with_global_quota_reserve(self):
        import copy
        ledger = self.recursive(4)
        for template_index, aid in ((3, "p2"), (4, "a2")):
            row = copy.deepcopy(ledger["assignments"][template_index])
            row.update(attempt_id=aid, wave=len(ledger["assignments"])+1,
                       coverage_cell=aid, overlap_key=aid)
            row["delegated_by"]["parent_call_id"] = f"call-{aid}"
            ledger["assignments"].append(row)
            ledger["assignments"][2]["planned_child_attempt_ids"].append(aid)
            ledger["assignments"][2]["collected_result_ids"].append(aid)
        for row in ledger["assignments"][:3]:
            row["descendant_budget"] += 2
        ledger.update(attempt_budget_N=8, verifier_reserve_V=2, concurrency_cap_C=6)
        self.assertEqual(CHECK._validate_tree_ledger(ledger)[0], [])

    def test_recursive_depth_limit_positive_integer_bounded_by_budget(self):
        for limit in (0, -1, True, 1.5, "4", 7):
            ledger = self.recursive()
            ledger["max_workflow_depth"] = limit
            self.assertTrue(any("max_workflow_depth" in e for e in self.check_recursive(ledger)))

    def test_recursive_too_deep_and_jump(self):
        ledger = self.recursive()
        ledger["max_workflow_depth"] = 3
        self.assertTrue(any("depth" in e for e in self.check_recursive(ledger)))
        ledger = self.recursive()
        ledger["assignments"][1]["depth"] = 3
        self.assertTrue(any("parent depth + 1" in e for e in self.check_recursive(ledger)))

    def test_recursive_false_root(self):
        ledger = self.recursive()
        row = ledger["assignments"][1]
        row.update(parent_attempt_id=None, root_parent_thread_uuid=row["parent_thread_uuid"], root_parent_call_id=row["parent_call_id"])
        self.assertTrue(any("top-level attempt depth" in e for e in self.check_recursive(ledger)))
        row["depth"] = 1
        row["delegated_by"].pop("parent_attempt_id")
        self.assertTrue(any("false root" in e for e in self.check_recursive(ledger)))

    def test_recursive_root_role_cannot_hide_concurrency(self):
        ledger = self.recursive()
        ledger["assignments"][0]["role"] = "root"
        ledger["concurrency_cap_C"] = 3
        errors = self.check_recursive(ledger)
        self.assertTrue(any("root is not a child attempt role" in e for e in errors))
        self.assertTrue(any("concurrency cap" in e for e in errors))

    def test_recursive_transitive_budget_inflation(self):
        ledger = self.recursive()
        ledger["assignments"][1]["descendant_budget"] += 1
        self.assertTrue(any("transitive descendant budget" in e for e in self.check_recursive(ledger)))
        ledger = self.recursive()
        ledger["assignments"][0]["descendant_budget"] += 1
        self.assertTrue(any("top-level subtree grants" in e for e in self.check_recursive(ledger)))

    def test_recursive_undelegated_coordinator(self):
        for value in (False, None):
            ledger = self.recursive()
            ledger["assignments"][1]["may_spawn_descendants"] = value
            self.assertTrue(any("explicit may_spawn_descendants" in e for e in self.check_recursive(ledger)))

    def test_recursive_leaf_assignment_stays_terminal(self):
        ledger = self.recursive()
        ledger["assignments"][1].update(role="builder", kind="builder", agent_role="luna_project_coordinator")
        self.assertTrue(any("non-coordinator may not spawn" in e for e in self.check_recursive(ledger)))

    def test_recursive_premature_collection_at_intermediate_level(self):
        ledger = self.recursive()
        row = ledger["assignments"][2]
        row.update(execution_status="started", acceptance_status="pending")
        row.pop("finished_at")
        self.assertTrue(any("child is not terminal" in e for e in self.check_recursive(ledger)))

    def test_recursive_direct_child_lists_cannot_skip_level(self):
        ledger = self.recursive()
        ledger["assignments"][0]["planned_child_attempt_ids"] = ["l1", "l2", "l3"]
        self.assertTrue(any("planned child list mismatch" in e for e in self.check_recursive(ledger)))

    def test_recursive_runtime_depth_and_parent_binding(self):
        ledger = self.recursive()
        row = ledger["assignments"][3]
        parent = ledger["assignments"][2]
        row.update(acceptance_status="accepted", thread_uuid=str(uuid.uuid4()),
                   runtime_turn=str(uuid.uuid4()), agent_role="default",
                   parent_thread_uuid=parent["thread_uuid"], parent_call_id="call-1", spawn_kind="spawn_agent")
        child_records = rollout_records(row["thread_uuid"], row["runtime_turn"], parent_id=parent["thread_uuid"])
        child_records[0]["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = 4
        parent_records = rollout_records(parent["thread_uuid"], str(uuid.uuid4()), parent_id=parent["parent_thread_uuid"])
        parent_records[0]["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = 3
        parent_records.extend([
            {"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent", "call_id": "call-1",
                "arguments": json.dumps({"task_name": "test_assignment", "agent_type": "default", "fork_turns": "none", "message": "bounded leaf"})}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": json.dumps({"agent_id": row["thread_uuid"]})}}])
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            sessions = home / "sessions"
            sessions.mkdir()
            cp = sessions / f"rollout-{row['thread_uuid']}.jsonl"
            pp = sessions / f"rollout-{parent['thread_uuid']}.jsonl"
            lp = home / "ledger.json"
            write_json(lp, ledger)
            write_jsonl(cp, child_records)
            write_jsonl(pp, parent_records)
            self.assertEqual(CHECK.validate_ledger_receipts(lp, home)[0], [])
            child_records[0]["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = 3
            write_jsonl(cp, child_records)
            self.assertTrue(any("runtime depth does not match" in e for e in CHECK.validate_ledger_receipts(lp, home)[0]))
            child_records[0]["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = 4
            write_jsonl(cp, child_records)
            parent_records[0]["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = 1
            write_jsonl(pp, parent_records)
            self.assertTrue(any("runtime parent depth" in e for e in CHECK.validate_ledger_receipts(lp, home)[0]))



class MixedCoordinatorCLITests(unittest.TestCase):
    def run_case(self, *, mixed=True, worker=True, policy_model="gpt-6-astra",
                 policy_effort="max", coordinator_model="gpt-6-astra",
                 actual_coordinator_model=None, leaf_model="gpt-5.6-luna",
                 actual_leaf_model=None, pin=True, nested=False, conflicting_kind=False,
                 coordinator_effort="max", actual_effort=None, spawn_effort=None, fork="none"):
        import contextlib
        import io
        rows = TreeV2Tests()._valid_rows()
        coord = rows[0]
        coord.update(agent_role="worker", runtime_model=coordinator_model, runtime_effort=coordinator_effort)
        root_id = coord["parent_thread_uuid"]
        for index, row in enumerate(rows[1:], 1):
            row.update(thread_uuid=str(uuid.uuid4()), runtime_turn=str(uuid.uuid4()),
                       parent_thread_uuid=coord["thread_uuid"], parent_call_id=f"call-{index}",
                       agent_role="worker", spawn_kind="spawn_agent", runtime_model=leaf_model,
                       runtime_effort="max")
        rows[1].update(acceptance_status="accepted", runtime_verified=True, safety_enforcement="prompt_only")
        if conflicting_kind:
            coord["kind"] = "evidence_lane"
        ledger = TreeV2Tests()._ledger(rows)
        policy = {"model": policy_model, "reasoning_effort": policy_effort}
        if nested:
            ledger["tree"] = {"coordinator_model_policy": policy}
        else:
            ledger["coordinator_model_policy"] = policy
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            sessions = home / "sessions"
            sessions.mkdir(parents=True)
            workspace = Path(temp) / "workspace"
            workspace.mkdir()
            (home / "config.toml").write_text("[agents]\nenabled=true\nmax_concurrent_threads_per_session=4\n", encoding="utf-8")
            def spawn(child, call, model):
                arguments = {"task_name": "test_assignment", "message": "bounded assignment",
                             "agent_type": "worker", "fork_turns": fork,
                             "reasoning_effort": (spawn_effort or coordinator_effort) if child == coord["thread_uuid"] else "max"}
                if pin:
                    arguments["model"] = model
                return [
                    {"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent",
                        "call_id": call, "arguments": json.dumps(arguments)}},
                    {"type": "response_item", "payload": {"type": "function_call_output", "call_id": call,
                        "output": json.dumps({"agent_id": child})}}]
            root = [{"type": "session_meta", "payload": {"id": root_id}}]
            root.extend(spawn(coord["thread_uuid"], "root-call", coordinator_model))
            write_jsonl(sessions / f"rollout-{root_id}.jsonl", root)
            records = rollout_records(coord["thread_uuid"], coord["runtime_turn"], role="worker", parent_id=root_id)
            records[1]["payload"]["model"] = actual_coordinator_model or coordinator_model
            records[1]["payload"]["effort"] = actual_effort or coordinator_effort
            completion = records.pop()
            for row in rows[1:]:
                records.extend(spawn(row["thread_uuid"], row["parent_call_id"], leaf_model))
            records.append(completion)
            write_jsonl(sessions / f"rollout-{coord['thread_uuid']}.jsonl", records)
            leaf = rows[1]
            records = rollout_records(leaf["thread_uuid"], leaf["runtime_turn"], role="worker", parent_id=coord["thread_uuid"])
            records[0]["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = 2
            records[1]["payload"]["model"] = actual_leaf_model or leaf_model
            write_jsonl(sessions / f"rollout-{leaf['thread_uuid']}.jsonl", records)
            path = Path(temp) / "ledger.json"
            write_json(path, ledger)
            argv = ["--codex-home", str(home), "--workspace", str(workspace), "--agent-role", "worker",
                    "--ledger-json", str(path), "--verify-ledger-receipts"]
            if mixed:
                argv.append("--allow-mixed-coordinators")
            if worker:
                argv.append("--allow-generic-worker")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = CHECK.main(argv)
            return code, output.getvalue()

    def test_mixed_coordinator_to_luna_leaf_cli(self):
        code, output = self.run_case()
        self.assertEqual(code, 0, output)
        self.assertIn("accepted runtime receipts passed revalidation", output)
        self.assertIn("model=gpt-6-astra", output)
        self.assertIn("model=gpt-5.6-luna", output)

    def test_mixed_coordinator_refused_by_default(self):
        code, output = self.run_case(mixed=False)
        self.assertNotEqual(code, 0)
        self.assertIn("--allow-mixed-coordinators", output)

    def test_mixed_worker_still_requires_both_flags_and_explicit_pins(self):
        for kwargs, expected in (({"worker": False}, "allow-generic-worker"), ({"pin": False}, "must explicitly set model")):
            code, output = self.run_case(**kwargs)
            self.assertNotEqual(code, 0)
            self.assertIn(expected, output)

    def test_mixed_policy_never_relaxes_leaf_model(self):
        for kwargs in ({"leaf_model": "gpt-6-astra"}, {"actual_leaf_model": "gpt-6-astra"}):
            code, output = self.run_case(**kwargs)
            self.assertNotEqual(code, 0)
            self.assertIn("must be 'gpt-5.6-luna'", output)

    def test_mixed_policy_runtime_mismatch(self):
        code, output = self.run_case(actual_coordinator_model="gpt-5.6-luna")
        self.assertNotEqual(code, 0)
        self.assertIn("runtime model must be 'gpt-6-astra'", output)

    def test_mixed_exact_effort_and_fresh_context_still_required(self):
        code, output = self.run_case(policy_effort="high", coordinator_effort="high")
        self.assertEqual(code, 0, output)
        for kwargs, expected in (
            ({"policy_effort": "high", "coordinator_effort": "high", "actual_effort": "max"}, "runtime reasoning effort"),
            ({"spawn_effort": "high"}, "reasoning_effort"),
            ({"fork": "all"}, "fork_turns")):
            code, output = self.run_case(**kwargs)
            self.assertNotEqual(code, 0)
            self.assertIn(expected, output)

    def test_mixed_unknown_policy_and_nested_alias_rejected(self):
        for kwargs in ({"policy_model": "unknown"}, {"policy_effort": "none"}, {"nested": True}):
            code, output = self.run_case(**kwargs)
            self.assertNotEqual(code, 0)
            self.assertIn("coordinator_model_policy", output)

    def test_mixed_coordinator_cannot_disguise_terminal_kind(self):
        code, output = self.run_case(conflicting_kind=True)
        self.assertNotEqual(code, 0)
        self.assertIn("coordinator role conflicts", output)

    def test_mixed_planning_can_describe_policy_without_opt_in(self):
        ledger = RecursiveTreeTests().recursive(3)
        ledger["coordinator_model_policy"] = {"model": "gpt-6-astra", "reasoning_effort": "high"}
        self.assertEqual(CHECK._validate_tree_ledger(ledger)[0], [])

    def test_mixed_exact_policy_keys_and_row_alias_rejected(self):
        ledger = RecursiveTreeTests().recursive(3)
        ledger["coordinator_model_policy"] = {"model": "gpt-6-astra", "reasoning_effort": "max", "fallback": True}
        self.assertTrue(any("exactly" in e for e in CHECK._validate_tree_ledger(ledger)[0]))
        ledger.pop("coordinator_model_policy")
        ledger["assignments"][1]["coordinator_model_policy"] = {"model": "gpt-6-astra", "reasoning_effort": "max"}
        self.assertTrue(any("top level" in e for e in CHECK._validate_tree_ledger(ledger)[0]))


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
    def test_nonaccepted_followup_is_a_counted_assignment(self):
        import copy
        ledger = self.base()
        original = ledger["assignments"][1]
        original.update(execution_status="completed", acceptance_status="rejected",
                        started_at="2026-01-01T00:01:00Z", finished_at="2026-01-01T00:02:00Z",
                        thread_uuid=str(uuid.uuid4()))
        followup = copy.deepcopy(original)
        followup.update(attempt_id="clarify", retry_of=original["attempt_id"], wave=3,
                        spawn_kind="followup_task", runtime_turn=None, retry_owner="root",
                        started_at="2026-01-01T00:03:00Z", finished_at="2026-01-01T00:04:00Z",
                        root_parent_call_id="call-followup", parent_call_id="call-followup",
                        gap_reason="Activation proof unavailable; root assesses sources separately")
        followup["delegated_by"]["parent_call_id"] = "call-followup"
        ledger["assignments"].append(followup)
        self.assertEqual(self.check(ledger)[0], [])
        ledger["attempt_budget_N"] = 3
        self.assertTrue(any("budget" in e or "attempts" in e for e in self.check(ledger)[0]))

    def test_unused_public_cells_close_without_fake_execution(self):
        ledger = self.base(phase="synthesis", closure_status="blocked")
        for row in ledger["assignments"]:
            row.update(execution_status="not_dispatched", acceptance_status="excluded",
                       started_at=None, finished_at="2026-01-01T00:02:00Z",
                       gap_reason="Source unavailable; no child evidence accepted")
        self.assertEqual(self.check(ledger)[0], [])
        ledger["assignments"][0]["execution_status"] = "planned"
        ledger["assignments"][0]["acceptance_status"] = "pending"
        self.assertTrue(any("planned/started" in e for e in self.check(ledger)[0]))

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


class ClosureRegressionTests(unittest.TestCase):
    def _project(self, statuses):
        rows = []
        for i, status in enumerate(statuses):
            row = project_assignment(f"v{i}", "verifier", status="completed", acceptance="accepted")
            row["acceptance_criteria"] = ["C1"]
            row["criterion_results"] = [{"criterion_id": "C1", "status": status,
                                         "evidence_locator": f"receipt:v{i}"}]
            rows.append(row)
        return {"version": 2, "phase": "closure", "closure_status": "complete",
                "overall_deadline": "2026-01-01T01:00:00Z",
                "root_integration_status": "completed", "root_integration_receipt": "receipt:root",
                "target_gate": "LOCAL_PASS", "verified_gates": ["LOCAL_PASS"],
                "gate_receipts": {"LOCAL_PASS": "receipt:local"}, "external_authority": False,
                "acceptance_criteria": ["C1"], "assignments": rows}

    def test_project_duplicate_results_cannot_hide_failure_in_either_order(self):
        for statuses in [("failed", "passed"), ("passed", "failed"), ("passed", "passed")]:
            with self.subTest(statuses=statuses):
                errors = CHECK._validate_project_v2_contract(self._project(statuses))
                self.assertTrue(any("duplicate criterion" in e for e in errors), errors)

    def test_project_single_passing_verdict_remains_valid(self):
        self.assertEqual(CHECK._validate_project_v2_contract(self._project(["passed"])), [])

    def test_nested_accepted_receipts_are_actually_reopened(self):
        row = project_assignment("v", "verifier", status="completed", acceptance="accepted")
        row["delegated_by"] = {"parent_thread_uuid": row["parent_thread_uuid"],
                               "parent_call_id": row["parent_call_id"]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            for key in ["assignments", "attempts"]:
                with self.subTest(key=key):
                    write_json(path, {"version": 2, "tree": {key: [row]}})
                    runtime_home = Path(temp) / "missing-home"
                    with patch.object(CHECK, "find_runtime_rollout", wraps=CHECK.find_runtime_rollout) as lookup:
                        errors, _ = CHECK.validate_ledger_receipts(path, runtime_home)
                    lookup.assert_called_once_with(runtime_home, row["thread_uuid"])
                    self.assertTrue(errors)

    def test_nested_rows_cannot_be_shadowed_by_empty_top_level(self):
        row = project_assignment("v", "verifier", status="completed", acceptance="accepted")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            value = {"version": 2, "tree": {"assignments": [row]}, "assignments": []}
            write_json(path, value)
            errors, _ = CHECK.validate_ledger_receipts(path, Path(temp))
            self.assertTrue(any("conflicting assignment" in e for e in errors), errors)
            errors, _ = CHECK._validate_tree_ledger(value)
            self.assertTrue(any("conflicting assignment" in e for e in errors), errors)

    def test_top_level_attempts_alias_cannot_shadow_assignments(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.json"
            write_json(path, {"version": 2, "attempts": [{"acceptance_status": "accepted"}], "assignments": []})
            errors, _ = CHECK.validate_ledger_receipts(path, Path(temp))
            self.assertTrue(any("conflicting assignment" in e for e in errors), errors)



class PeerCollaborationTests(unittest.TestCase):
    def fixture(self):
        revision = "a" * 64
        return {"closure_status": "complete", "collaboration": {
            "mode": "bounded_peer", "message_budget": 8, "round_limit": 2,
            "peer_links": [{"from": "B", "to": "R"}, {"from": "R", "to": "B"}],
            "issues": [{"id": "I", "owner": "B", "reviewer": "R", "state": "verified",
                        "blocking": True, "revision": revision, "verified_revision": revision,
                        "resolution_receipt": "call:verify"}],
            "messages": [
                {"id": "m1", "from": "B", "to": "R", "issue_id": "I", "type": "candidate", "round": 1, "revision": revision, "receipt": "call:candidate"},
                {"id": "m2", "from": "R", "to": "B", "issue_id": "I", "type": "verification", "status": "passed", "round": 1, "revision": revision, "receipt": "call:verify"}]
        }}

    def check(self, value):
        return CHECK._validate_collaboration(value, [{"attempt_id": "B"}, {"attempt_id": "R"}])

    def test_verified_peer_exchange(self):
        self.assertEqual(self.check(self.fixture()), [])

    def test_existing_nonpeer_ledger_remains_supported(self):
        self.assertEqual(self.check({}), [])

    def test_nested_peer_record_cannot_bypass_validation(self):
        x = self.fixture()
        x["tree"] = {"collaboration": x.pop("collaboration")}
        self.assertTrue(any("top level" in e for e in self.check(x)))

    def test_unresolved_issue_blocks_closure(self):
        x = self.fixture(); x["collaboration"]["issues"][0]["state"] = "acknowledged"
        self.assertTrue(any("unresolved" in e for e in self.check(x)))

    def test_stale_verification_rejected(self):
        x = self.fixture(); x["collaboration"]["issues"][0]["revision"] = "b" * 64
        self.assertTrue(any("stale" in e for e in self.check(x)))

    def test_later_candidate_invalidates_verification(self):
        x = self.fixture(); x["collaboration"]["messages"].append(dict(x["collaboration"]["messages"][0], id="m3", revision="b" * 64))
        self.assertTrue(any("lacks owner candidate" in e for e in self.check(x)))

    def test_owner_cannot_verify_own_candidate(self):
        x = self.fixture(); x["collaboration"]["messages"][1].update({"from": "B", "to": "R"})
        self.assertTrue(any("must come from reviewer" in e for e in self.check(x)))

    def test_verification_before_candidate_rejected(self):
        x = self.fixture(); x["collaboration"]["messages"].reverse()
        self.assertTrue(self.check(x))

    def test_unauthorized_peer_link_rejected(self):
        x = self.fixture(); x["collaboration"]["peer_links"] = []
        self.assertTrue(any("unauthorized" in e for e in self.check(x)))

    def test_unknown_peer_rejected(self):
        x = self.fixture(); x["collaboration"]["messages"][0]["to"] = "missing"
        self.assertTrue(any("participants" in e for e in self.check(x)))

    def test_message_and_round_budgets_enforced(self):
        x = self.fixture(); x["collaboration"]["message_budget"] = 1
        x["collaboration"]["messages"][0]["round"] = 3
        errors = self.check(x)
        self.assertTrue(any("message budget" in e for e in errors))
        self.assertTrue(any("round limit" in e for e in errors))

    def test_blocking_issue_cannot_be_deferred(self):
        x = self.fixture(); x["collaboration"]["issues"][0].update(state="deferred", root_decision="root:defer")
        self.assertTrue(any("cannot defer" in e for e in self.check(x)))

    def test_nonblocking_explicit_root_deferral(self):
        x = self.fixture(); x["collaboration"]["issues"][0].update(state="deferred", blocking=False, root_decision="root:defer")
        self.assertEqual(self.check(x), [])

    def test_malformed_peer_fields_return_errors(self):
        for field in ["owner", "reviewer", "state", "revision"]:
            with self.subTest(field=field):
                x = self.fixture(); x["collaboration"]["issues"][0][field] = []
                self.assertTrue(self.check(x))
        for field in ["from", "to", "type", "id", "issue_id"]:
            with self.subTest(field=field):
                x = self.fixture(); x["collaboration"]["messages"][0][field] = []
                self.assertTrue(self.check(x))

    def test_project_closure_invokes_peer_guard(self):
        x = ClosureRegressionTests()._project(["passed"])
        c = self.fixture()["collaboration"]
        c["issues"][0]["state"] = "open"
        x["collaboration"] = c
        self.assertTrue(any("unresolved" in e for e in CHECK._validate_project_v2_contract(x)))

    def test_new_finding_or_interface_change_reopens_issue(self):
        for kind in ["finding", "interface_change"]:
            with self.subTest(kind=kind):
                x = self.fixture()
                x["collaboration"]["messages"].append(dict(x["collaboration"]["messages"][1], id="m3", type=kind))
                self.assertTrue(any("lacks owner candidate" in e for e in self.check(x)))

    def test_failed_or_blocked_verification_cannot_close(self):
        for status in ["failed", "blocked", None]:
            with self.subTest(status=status):
                x = self.fixture(); x["collaboration"]["messages"][1]["status"] = status
                self.assertTrue(self.check(x))

    def test_later_failed_verification_revokes_pass(self):
        x = self.fixture()
        x["collaboration"]["messages"].append(dict(x["collaboration"]["messages"][1], id="m3", status="failed"))
        self.assertTrue(self.check(x))


class V2ActivationTests(unittest.TestCase):
    def record(self, with_v2=True):
        self.initial, self.followup = str(uuid.uuid4()), str(uuid.uuid4())
        records = rollout_records(str(uuid.uuid4()), self.initial)
        if with_v2:
            records[0]["payload"]["multi_agent_version"] = "v2"
        records += [
            {"type": "turn_context", "payload": {"turn_id": self.followup, "model": "gpt-5.6-luna", "effort": "max", "sandbox_policy": {"type": "read-only"}}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": self.followup}}]
        return records

    def test_initial_turn_still_valid_with_later_turn(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"child.jsonl"; write_jsonl(p,self.record())
            errors,_ = CHECK.validate_runtime_rollout(p,"default",runtime_turn=self.initial,require_initial_turn=True,require_v2=True)
            self.assertEqual(errors, [])

    def test_followup_cannot_borrow_initial_spawn_proof(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"child.jsonl"; write_jsonl(p,self.record())
            errors,_=CHECK.validate_runtime_rollout(p,"default",runtime_turn=self.followup,require_initial_turn=True)
            self.assertTrue(any("initial child turn" in e for e in errors))

    def test_metadata_only_followup_check_is_supported(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"child.jsonl"; write_jsonl(p,self.record())
            errors,_=CHECK.validate_runtime_rollout(p,"default",runtime_turn=self.followup)
            self.assertEqual(errors, [])

    def test_v2_runtime_must_be_evidenced_when_required(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"child.jsonl"; write_jsonl(p,self.record(False))
            errors,_=CHECK.validate_runtime_rollout(p,"default",runtime_turn=self.initial,require_v2=True)
            self.assertTrue(any("multi_agent_version" in e for e in errors))

    def test_missing_turn_id_is_error_not_crash_with_initial_guard(self):
        with tempfile.TemporaryDirectory() as d:
            records=self.record(); records[1]["payload"].pop("turn_id")
            p=Path(d)/"child.jsonl"; write_jsonl(p,records)
            errors,_=CHECK.validate_runtime_rollout(p,"default",runtime_turn=self.followup,require_initial_turn=True)
            self.assertTrue(errors)

    def test_malformed_initial_context_cannot_hide_followup(self):
        with tempfile.TemporaryDirectory() as d:
            records=self.record(); records[1]["payload"]=[]
            p=Path(d)/"child.jsonl"; write_jsonl(p,records)
            errors,_=CHECK.validate_runtime_rollout(p,"default",runtime_turn=self.followup,require_initial_turn=True)
            self.assertTrue(any("invalid runtime metadata" in e for e in errors))

    def test_nonobject_jsonl_returns_structured_error(self):
        for value in [[],None,1,"bad"]:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as d:
                p=Path(d)/"child.jsonl"; write_jsonl(p,[value])
                errors,_=CHECK.validate_runtime_rollout(p,"default",require_initial_turn=True)
                self.assertTrue(any("expected object" in e for e in errors))


if __name__ == "__main__":
    unittest.main(module=__name__)
