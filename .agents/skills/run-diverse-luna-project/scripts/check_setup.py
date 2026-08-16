#!/usr/bin/env python3
"""Fail-closed static, schema, rollout, and optional research-ledger checks."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

EXPECTED_MODEL = "gpt-5.6-luna"
EXPECTED_REASONING_EFFORT = "medium"
CHECKER_CONTRACT_VERSION = "2026-08-17.1"
MIN_CONCURRENT_THREADS = 2
READ_ONLY_SANDBOXES = {"read-only", "read_only", "readonly"}
SOURCE_PLANES = {
    "public_web",
    "local",
    "internal_session",
    "connector_private",
    "provider",
}
QUOTA_LABELS = {"primary", "adversarial", "measurement_gap", "other"}
EXECUTION_STATES = {
    "planned",
    "not_dispatched",
    "started",
    "completed",
    "failed",
    "timed_out",
    "abandoned",
}
ACCEPTANCE_STATES = {"pending", "accepted", "rejected", "excluded"}
ACCESS_MODES = {"sandbox_read_only", "prompt_only_public", "root_only"}
SAFETY_ENFORCEMENT = {"sandbox_read_only", "prompt_only", "unknown"}
PROJECT_KINDS = {
    "coordinator",
    "builder",
    "evidence_lane",
    "reviewer",
    "verifier",
    "operator",
}
INTEGRATION_STATES = {"not_applicable", "pending", "integrated", "rejected"}
ROOT_INTEGRATION_STATES = {"not_started", "in_progress", "completed", "blocked"}
VERIFIED_GATE_ORDER = (
    "LOCAL_PASS",
    "DEVICE_PASS",
    "PROVIDER_PASS",
    "PUBLIC_PASS",
    "HUMAN_GO",
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on old Python only
    print("ERROR: Python 3.11+ is required (tomllib is unavailable).")
    raise SystemExit(2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a skill-local GPT-5.6 Luna/medium subagent route."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {CHECKER_CONTRACT_VERSION}",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home containing config.toml, agents, and sessions.",
    )
    parser.add_argument(
        "--config",
        action="append",
        type=Path,
        default=[],
        help="Optional config overlay, repeatable in increasing precedence order.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace whose ancestor .codex layers are checked for overrides.",
    )
    parser.add_argument(
        "--agent-role",
        default="default",
        help="Selected spawn agent_type or custom agent role. Default: default.",
    )
    parser.add_argument(
        "--allow-generic-worker",
        action="store_true",
        help=(
            "Explicitly opt in to the built-in worker role; requires a fresh "
            "route with explicit model=gpt-5.6-luna and reasoning_effort=medium."
        ),
    )
    parser.add_argument(
        "--spawn-schema-json",
        type=Path,
        help="Optional captured tool-schema JSON containing spawn_agent.",
    )
    parser.add_argument(
        "--ledger-json",
        type=Path,
        help="Optional machine-readable research or project assignment ledger.",
    )
    parser.add_argument(
        "--verify-ledger-receipts",
        action="store_true",
        help="Resolve and validate every accepted ledger row against its child rollout.",
    )
    parser.add_argument(
        "--require-read-only",
        action="store_true",
        help="Reject a runtime receipt unless the effective child sandbox is read-only.",
    )
    runtime = parser.add_mutually_exclusive_group()
    runtime.add_argument(
        "--runtime-rollout",
        type=Path,
        help="Completed child-agent JSONL rollout to verify.",
    )
    runtime.add_argument(
        "--runtime-thread",
        help="Child thread UUID; locate its rollout below CODEX_HOME/sessions.",
    )
    parser.add_argument(
        "--runtime-turn",
        help="Exact child turn UUID to verify inside the selected rollout; defaults to latest.",
    )
    parser.add_argument(
        "--parent-rollout",
        type=Path,
        help="Optional parent JSONL used to prove the exact spawn request route.",
    )
    parser.add_argument(
        "--require-spawn-provenance",
        action="store_true",
        help="Require a unique matching parent spawn request for the child receipt.",
    )
    return parser.parse_args(argv)


def load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read TOML {path}: {exc}") from exc


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_config(current, value)
        else:
            merged[key] = value
    return merged


def iter_agent_dirs(workspace: Path, codex_home: Path) -> Iterable[Path]:
    candidates = [codex_home / "agents"]
    candidates.extend(
        directory / ".codex" / "agents"
        for directory in (workspace, *workspace.parents)
    )
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            resolved = candidate.expanduser().absolute()
        if resolved not in seen:
            seen.add(resolved)
            yield resolved


def load_role_definitions(
    workspace: Path, codex_home: Path, role_name: str
) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    definitions: list[tuple[Path, dict[str, Any]]] = []
    warnings: list[str] = []
    for agents_dir in iter_agent_dirs(workspace, codex_home):
        if not agents_dir.is_dir():
            continue
        try:
            role_paths = sorted(agents_dir.rglob("*.toml"))
        except OSError as exc:
            warnings.append(f"cannot scan {agents_dir}: {exc}")
            continue
        for role_path in role_paths:
            try:
                role = load_toml(role_path)
            except ValueError as exc:
                warnings.append(str(exc))
                continue
            if role.get("name") == role_name:
                definitions.append((role_path.resolve(), role))
    return definitions, warnings


def validate_static_base(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    agents = config.get("agents")
    if not isinstance(agents, dict):
        errors.append("[agents] must be a TOML table")
        return errors, warnings

    if agents.get("enabled") is not True:
        errors.append(f"agents.enabled must be true, got {agents.get('enabled')!r}")
    else:
        print("OK: configured agents.enabled = true")

    current_threads = agents.get("max_concurrent_threads_per_session")
    if current_threads is None:
        warnings.append(
            "agents.max_concurrent_threads_per_session is unset; inspect live "
            "capacity before choosing a wave size"
        )
    elif (
        not isinstance(current_threads, int)
        or isinstance(current_threads, bool)
        or current_threads < MIN_CONCURRENT_THREADS
    ):
        errors.append(
            "agents.max_concurrent_threads_per_session must be at least "
            f"{MIN_CONCURRENT_THREADS} for parallel research, got {current_threads!r}"
        )
    else:
        print(
            "OK: configured agents.max_concurrent_threads_per_session = "
            f"{current_threads}"
        )

    if "max_threads" in agents:
        warnings.append(
            "agents.max_threads is a legacy alias; prefer "
            "agents.max_concurrent_threads_per_session and do not set both"
        )
        if "max_concurrent_threads_per_session" in agents:
            errors.append(
                "[agents] sets both max_threads and "
                "max_concurrent_threads_per_session"
            )
    if "max_depth" in agents:
        warnings.append(
            "agents.max_depth is not listed in the current official Codex "
            "subagent settings; treat it as an unverified local extension, "
            "not an enforced depth receipt"
        )
    return errors, warnings


def validate_role_policy(
    config: dict[str, Any],
    definitions: list[tuple[Path, dict[str, Any]]],
    role_name: str,
    allow_generic_worker: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    agents = config.get("agents")
    agents = agents if isinstance(agents, dict) else {}

    config_model = agents.get("default_subagent_model")
    config_effort = agents.get("default_subagent_reasoning_effort")
    config_pin = (
        role_name == "default"
        and config_model == EXPECTED_MODEL
        and config_effort == EXPECTED_REASONING_EFFORT
    )

    if role_name == "worker" and allow_generic_worker:
        if definitions:
            errors.append("generic worker mode must not pretend a custom TOML definition exists")
        warnings.append(
            "generic worker mode is explicitly enabled; runtime and parent provenance "
            "must prove exact Luna/medium fields"
        )
        return errors, warnings
    if role_name == "worker" and not allow_generic_worker:
        errors.append(
            "built-in generic worker is disabled by default; pass --allow-generic-worker "
            "for an explicit Luna/medium fresh-context route"
        )
        return errors, warnings

    role_pin = False
    for path, role in definitions:
        for required in ("name", "description", "developer_instructions"):
            if not isinstance(role.get(required), str) or not role[required].strip():
                errors.append(f"{path}: custom role requires non-empty {required}")
        model = role.get("model", config_model)
        effort = role.get("model_reasoning_effort", config_effort)
        if model != EXPECTED_MODEL:
            errors.append(
                f"{path}: role {role_name!r} model must be "
                f"{EXPECTED_MODEL!r}, got {model!r}"
            )
        if effort != EXPECTED_REASONING_EFFORT:
            errors.append(
                f"{path}: role {role_name!r} reasoning effort must be "
                f"{EXPECTED_REASONING_EFFORT!r}, got {effort!r}"
            )
        if model == EXPECTED_MODEL and effort == EXPECTED_REASONING_EFFORT:
            role_pin = True
            sandbox = role.get("sandbox_mode")
            print(
                f"OK: {path} pins role={role_name}, model={model}, "
                f"reasoning_effort={effort}, static_sandbox={sandbox!r}"
            )

    if role_name != "default" and not definitions:
        errors.append(f"no custom agent definition found for role {role_name!r}")
    if not config_pin and not role_pin:
        errors.append(
            f"selected role {role_name!r} is not statically pinned to "
            f"{EXPECTED_MODEL}/{EXPECTED_REASONING_EFFORT}"
        )
    elif config_pin:
        print(
            "OK: [agents] default route is pinned by this skill's local policy "
            f"to {EXPECTED_MODEL}/{EXPECTED_REASONING_EFFORT}"
        )

    if role_name == "default" and role_pin and not config_pin:
        warnings.append(
            "[agents] defaults are not Luna/medium, but the selected custom "
            "default role is pinned; completed-rollout verification remains required"
        )
    return errors, warnings


def validate_workspace_config_overrides(
    workspace: Path, codex_home: Path, role_name: str
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    checked: set[Path] = set()
    codex_home = codex_home.expanduser().resolve()

    for directory in (workspace, *workspace.parents):
        config_path = directory / ".codex" / "config.toml"
        try:
            resolved = config_path.resolve()
        except OSError:
            resolved = config_path.absolute()
        if resolved == codex_home / "config.toml" or resolved in checked:
            continue
        if not config_path.is_file():
            continue
        checked.add(resolved)
        try:
            layer = load_toml(config_path)
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        agents = layer.get("agents")
        if not isinstance(agents, dict):
            continue
        if agents.get("enabled") is False:
            errors.append(f"{config_path}: agents.enabled disables subagents")
        value = agents.get("max_concurrent_threads_per_session")
        if value is not None and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < MIN_CONCURRENT_THREADS
        ):
            errors.append(
                f"{config_path}: agents.max_concurrent_threads_per_session "
                f"must be at least {MIN_CONCURRENT_THREADS}, got {value!r}"
            )
        if role_name == "default":
            expected = {
                "default_subagent_model": EXPECTED_MODEL,
                "default_subagent_reasoning_effort": EXPECTED_REASONING_EFFORT,
            }
            for key, required in expected.items():
                if key in agents and agents[key] != required:
                    errors.append(
                        f"{config_path}: agents.{key} conflicts with the "
                        f"skill-local {required!r} acceptance policy"
                    )

    if checked and not errors:
        print(f"OK: {len(checked)} workspace config layer(s) passed override checks")
    elif not checked:
        print("OK: no workspace config layer shadows the selected Luna route")
    return errors, warnings


def spawn_agent_schemas(
    value: object, *, _seen: set[int] | None = None, _depth: int = 0
) -> list[dict[str, Any]]:
    if _depth > 64:
        return []
    if _seen is None:
        _seen = set()
    object_id = id(value)
    if object_id in _seen:
        return []
    if isinstance(value, (dict, list)):
        _seen.add(object_id)

    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        name = value.get("name")
        if (
            isinstance(name, str)
            and (
                name == "spawn_agent"
                or name.endswith(".spawn_agent")
                or name.endswith("__spawn_agent")
            )
            and any(
                isinstance(value.get(key), dict)
                for key in ("parameters", "inputSchema", "input_schema")
            )
        ):
            found.append(value)
        for child in value.values():
            found.extend(
                spawn_agent_schemas(child, _seen=_seen, _depth=_depth + 1)
            )
    elif isinstance(value, list):
        for child in value:
            found.extend(
                spawn_agent_schemas(child, _seen=_seen, _depth=_depth + 1)
            )
    return found


def _schema_route_variants(
    schema: dict[str, Any], *, _depth: int = 0
) -> list[tuple[dict[str, Any], set[str]]]:
    """Return property/required pairs without unioning oneOf/anyOf branches."""
    if _depth > 32:
        return []
    direct = schema.get("properties")
    base = dict(direct) if isinstance(direct, dict) else {}
    raw_required = schema.get("required")
    required = {
        value for value in raw_required if isinstance(value, str)
    } if isinstance(raw_required, list) else set()
    variants: list[tuple[dict[str, Any], set[str]]] = [(base, required)]

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for member in all_of:
            if not isinstance(member, dict):
                continue
            member_variants = _schema_route_variants(member, _depth=_depth + 1)
            if not member_variants:
                continue
            variants = [
                ({**left_props, **right_props}, left_required | right_required)
                for left_props, left_required in variants
                for right_props, right_required in member_variants
            ]

    alternatives: list[tuple[dict[str, Any], set[str]]] = []
    for key in ("oneOf", "anyOf"):
        members = schema.get(key)
        if isinstance(members, list):
            for member in members:
                if isinstance(member, dict):
                    alternatives.extend(
                        _schema_route_variants(member, _depth=_depth + 1)
                    )
    if alternatives:
        variants = [
            ({**base_props, **alt_props}, base_required | alt_required)
            for base_props, base_required in variants
            for alt_props, alt_required in alternatives
        ]
    return [(properties, needed) for properties, needed in variants if properties]


def spawn_agent_route_variants(
    schema: dict[str, Any],
) -> list[tuple[dict[str, Any], set[str]]]:
    variants: list[tuple[dict[str, Any], set[str]]] = []
    for key in ("parameters", "inputSchema", "input_schema"):
        candidate = schema.get(key)
        if isinstance(candidate, dict):
            variants.extend(_schema_route_variants(candidate))
    return variants


def spawn_agent_property_variants(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [properties for properties, _ in spawn_agent_route_variants(schema)]


def spawn_agent_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Compatibility helper: return the first non-empty property variant."""
    variants = spawn_agent_property_variants(schema)
    return variants[0] if variants else {}


def _json_type_allows(type_name: object, expected: object) -> bool:
    if type_name == "string":
        return isinstance(expected, str)
    if type_name == "boolean":
        return isinstance(expected, bool)
    if type_name == "integer":
        return isinstance(expected, int) and not isinstance(expected, bool)
    if type_name == "number":
        return isinstance(expected, (int, float)) and not isinstance(expected, bool)
    if type_name == "null":
        return expected is None
    if type_name == "array":
        return isinstance(expected, list)
    if type_name == "object":
        return isinstance(expected, dict)
    return False


def _constraint_allows(property_schema: object, expected: object) -> bool:
    """Return whether a literal is admitted by the observable JSON Schema subset.

    Unknown references fail closed. An empty schema and boolean ``true`` are valid
    JSON Schema forms that admit every value; malformed property schemas do not.
    """
    if property_schema is True:
        return True
    if property_schema is False or not isinstance(property_schema, dict):
        return False
    if "$ref" in property_schema:
        return False

    all_of = property_schema.get("allOf")
    if isinstance(all_of, list) and not all(
        _constraint_allows(item, expected) for item in all_of
    ):
        return False
    any_of = property_schema.get("anyOf")
    if isinstance(any_of, list) and not any(
        _constraint_allows(item, expected) for item in any_of
    ):
        return False
    one_of = property_schema.get("oneOf")
    if isinstance(one_of, list) and sum(
        _constraint_allows(item, expected) for item in one_of
    ) != 1:
        return False
    if "not" in property_schema and _constraint_allows(
        property_schema["not"], expected
    ):
        return False

    if "const" in property_schema and property_schema["const"] != expected:
        return False
    values = property_schema.get("enum")
    if isinstance(values, list) and expected not in values:
        return False

    declared_type = property_schema.get("type")
    if isinstance(declared_type, list):
        if not any(_json_type_allows(item, expected) for item in declared_type):
            return False
    elif declared_type is not None and not _json_type_allows(
        declared_type, expected
    ):
        return False

    if isinstance(expected, str):
        minimum = property_schema.get("minLength")
        maximum = property_schema.get("maxLength")
        if isinstance(minimum, int) and len(expected) < minimum:
            return False
        if isinstance(maximum, int) and len(expected) > maximum:
            return False
        pattern = property_schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, expected) is None:
                    return False
            except re.error:
                return False
    return True


def _constraint_is_explicit(property_schema: object) -> bool:
    return property_schema is True or (
        isinstance(property_schema, dict) and bool(property_schema)
    )


def _routes_for_variant(
    properties: dict[str, Any], role_name: str
) -> tuple[list[str], list[str]]:
    routes: list[str] = []
    warnings: list[str] = []
    if "message" not in properties:
        return routes, warnings

    agent_type = properties.get("agent_type")
    if "fork_turns" in properties and _constraint_allows(
        properties["fork_turns"], "none"
    ):
        role_ok = role_name == "default" and "agent_type" not in properties
        if "agent_type" in properties:
            role_ok = _constraint_allows(agent_type, role_name)
        if role_ok:
            routes.append(f"fork_turns=none, agent_type={role_name}")
            if not _constraint_is_explicit(properties["fork_turns"]):
                warnings.append(
                    "fork_turns is not enum/const constrained; verify that "
                    'the live call accepts "none"'
                )
            if "agent_type" in properties and not _constraint_is_explicit(agent_type):
                warnings.append(
                    f"agent_type is not enum/const constrained; verify role {role_name!r}"
                )

    if {
        "agent_type",
        "fork_context",
    }.issubset(properties) and _constraint_allows(
        properties["agent_type"], role_name
    ) and _constraint_allows(
        properties["fork_context"], False
    ):
        routes.append(f"agent_type={role_name}, fork_context=false")
        if not _constraint_is_explicit(properties["fork_context"]):
            warnings.append(
                "fork_context is not enum/const constrained; verify that "
                "the live call accepts false"
            )
        if not _constraint_is_explicit(properties["agent_type"]):
            warnings.append(
                f"agent_type is not enum/const constrained; verify role {role_name!r}"
            )
    return routes, warnings


def validate_spawn_schema(
    path: Path, role_name: str
) -> tuple[list[str], list[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read spawn schema JSON {path}: {exc}"], []

    schemas = spawn_agent_schemas(document)
    if not schemas:
        return [f"{path} contains no spawn_agent declaration"], []

    routes: list[str] = []
    warnings: list[str] = []
    fields_seen: list[tuple[list[str], list[str]]] = []
    for schema in schemas:
        for properties, required in spawn_agent_route_variants(schema):
            fields_seen.append((sorted(properties), sorted(required)))
            if not {"task_name", "message"}.issubset(properties):
                continue
            if not {"task_name", "message"}.issubset(required):
                continue
            variant_routes, variant_warnings = _routes_for_variant(
                properties, role_name
            )
            routes.extend(variant_routes)
            warnings.extend(variant_warnings)

    if not fields_seen or not any(
        {"task_name", "message"}.issubset(fields) for fields, _ in fields_seen
    ):
        return ["spawn_agent schema does not expose task_name and message"], []
    if not routes:
        rendered = " | ".join(
            f"properties=[{', '.join(fields)}] required=[{', '.join(required)}]"
            for fields, required in fields_seen
        )
        return [
            "no single spawn_agent schema variant requires task_name/message and "
            "supports the selected role plus a non-history route; variants: "
            f"{rendered}"
        ], warnings

    print("OK: complete non-history route(s): " + "; ".join(sorted(set(routes))))
    return [], sorted(set(warnings))


def rollout_has_thread(path: Path, thread_id: str) -> bool:
    matching = 0
    metadata_count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                document = json.loads(line)
                if document.get("type") == "session_meta":
                    payload = document.get("payload")
                    metadata_count += 1
                    if isinstance(payload, dict) and payload.get("id") == thread_id:
                        matching += 1
    except (OSError, json.JSONDecodeError):
        return False
    return metadata_count == 1 and matching == 1


def find_runtime_rollout(codex_home: Path, thread_id: str) -> Path:
    try:
        normalized = str(uuid.UUID(thread_id))
    except ValueError as exc:
        raise ValueError(f"runtime thread must be a UUID, got {thread_id!r}") from exc
    sessions = codex_home / "sessions"
    if not sessions.is_dir():
        raise ValueError(f"sessions directory is missing: {sessions}")
    fast_matches = sorted(
        path.resolve()
        for path in sessions.rglob(f"*{normalized}.jsonl")
        if rollout_has_thread(path, normalized)
    )
    matches = fast_matches
    if not matches:
        matches = sorted(
            path.resolve()
            for path in sessions.rglob("*.jsonl")
            if rollout_has_thread(path, normalized)
        )
    if not matches:
        raise ValueError(f"no child rollout found for thread {normalized}")
    if len(matches) > 1:
        rendered = ", ".join(str(path) for path in matches)
        raise ValueError(
            f"ambiguous child rollout for thread {normalized}; matches: {rendered}"
        )
    return matches[0]


def _sandbox_name(context: dict[str, Any]) -> str | None:
    policy = context.get("sandbox_policy")
    if isinstance(policy, str):
        return policy
    if isinstance(policy, dict):
        value = policy.get("type") or policy.get("mode")
        return value if isinstance(value, str) else None
    return None


def _spawn_metadata(
    session_meta: dict[str, Any],
) -> tuple[object, object, object, object]:
    source = session_meta.get("source")
    if not isinstance(source, dict):
        return None, None, None, None
    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return None, None, None, None
    spawn = subagent.get("thread_spawn")
    if not isinstance(spawn, dict):
        return None, None, None, None
    return (
        spawn.get("depth"),
        spawn.get("parent_thread_id"),
        spawn.get("agent_role"),
        spawn.get("agent_path"),
    )


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _canonical_uuid(value: object) -> bool:
    """Accept only string UUIDs in canonical hyphenated form."""
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _parse_timestamp(value: object) -> datetime | None:
    if not _valid_timestamp(value):
        return None
    assert isinstance(value, str)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _state_errors(prefix: str, execution: object, acceptance: object) -> list[str]:
    allowed = {
        "planned": {"pending"},
        "not_dispatched": {"excluded"},
        "started": {"pending"},
        "completed": {"accepted", "rejected"},
        "failed": {"excluded"},
        "timed_out": {"excluded"},
        "abandoned": {"excluded"},
    }
    if execution not in allowed or acceptance not in ACCEPTANCE_STATES:
        return []
    if acceptance in allowed[execution]:
        return []
    expected = " or ".join(sorted(allowed[execution]))
    return [
        f"{prefix}: execution_status={execution} requires "
        f"acceptance_status={expected}, got {acceptance!r}"
    ]


def _deadline_errors(
    prefix: str,
    execution: object,
    acceptance: object,
    started_at: datetime | None,
    ended_at: datetime | None,
    assignment_deadline: datetime | None,
    overall_deadline: datetime | None,
) -> list[str]:
    """Reject work started too late and accepted output completed too late."""
    errors: list[str] = []
    active_states = {"started", "completed", "failed", "timed_out", "abandoned"}
    if execution in active_states:
        if started_at is not None and assignment_deadline is not None and started_at > assignment_deadline:
            errors.append(f"{prefix}: started_at exceeds assignment deadline")
        if started_at is not None and overall_deadline is not None and started_at > overall_deadline:
            errors.append(f"{prefix}: started_at exceeds overall_deadline")
    if acceptance == "accepted" and ended_at is not None:
        if assignment_deadline is not None and ended_at > assignment_deadline:
            errors.append(f"{prefix}: accepted completion exceeds assignment deadline")
        if overall_deadline is not None and ended_at > overall_deadline:
            errors.append(f"{prefix}: accepted completion exceeds overall_deadline")
    return errors


def _access_errors(
    prefix: str,
    plane: object,
    access_mode: object,
    execution: object,
    acceptance: object,
    safety: object,
    runtime_verified: object,
    thread_uuid: object,
    gap_reason: object = None,
) -> list[str]:
    errors: list[str] = []
    if plane in {"connector_private", "provider"} and access_mode != "root_only":
        errors.append(
            f"{prefix}: {plane} evidence must remain root_only because this checker "
            "cannot prove external connector/provider tool permissions"
        )
    if access_mode == "prompt_only_public":
        if plane != "public_web":
            errors.append(
                f"{prefix}: prompt_only_public is allowed only for source_plane=public_web"
            )
        if acceptance == "accepted" and safety != "prompt_only":
            errors.append(
                f"{prefix}: accepted prompt_only_public result requires "
                "safety_enforcement=prompt_only"
            )
    if access_mode == "sandbox_read_only":
        if plane in {"connector_private", "provider"}:
            errors.append(
                f"{prefix}: filesystem sandbox_read_only does not prove external "
                f"{plane} tools are read-only"
            )
        if acceptance == "accepted" and safety != "sandbox_read_only":
            errors.append(
                f"{prefix}: accepted sandbox_read_only result requires matching "
                "filesystem sandbox enforcement"
            )
    if access_mode == "root_only":
        valid_root_only_state = (
            (execution == "planned" and acceptance == "pending")
            or (execution == "not_dispatched" and acceptance == "excluded")
        )
        if not valid_root_only_state:
            errors.append(
                f"{prefix}: root_only rows must remain planned/pending or close "
                "as not_dispatched/excluded"
            )
        if runtime_verified is not False or thread_uuid is not None:
            errors.append(
                f"{prefix}: root_only rows cannot carry child runtime evidence"
            )
        if execution == "not_dispatched" and (
            not isinstance(gap_reason, str) or not gap_reason.strip()
        ):
            errors.append(
                f"{prefix}: not_dispatched root_only row requires a non-empty gap_reason"
            )
    if acceptance == "accepted" and safety == "unknown":
        errors.append(f"{prefix}: accepted result cannot use unknown safety enforcement")
    return errors


def _accepted_runtime_errors(prefix: str, row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("runtime_verified") is not True or not _canonical_uuid(row.get("thread_uuid")):
        errors.append(
            f"{prefix}: accepted result requires runtime_verified=true and thread_uuid"
        )
    for key in ("thread_uuid", "runtime_turn", "parent_thread_uuid"):
        if not _canonical_uuid(row.get(key)):
            errors.append(f"{prefix}: accepted result requires a {key} UUID")
    if row.get("runtime_model") != EXPECTED_MODEL:
        errors.append(
            f"{prefix}: accepted runtime_model must be {EXPECTED_MODEL!r}"
        )
    if row.get("runtime_effort") != EXPECTED_REASONING_EFFORT:
        errors.append(
            f"{prefix}: accepted runtime_effort must be "
            f"{EXPECTED_REASONING_EFFORT!r}"
        )
    if not isinstance(row.get("agent_role"), str) or not row["agent_role"].strip():
        errors.append(f"{prefix}: accepted result requires agent_role")
    if row.get("spawn_kind") != "spawn_agent":
        errors.append(
            f"{prefix}: accepted result requires spawn_kind='spawn_agent'; "
            "follow-up acceptance is unsupported"
        )
    if not isinstance(row.get("parent_call_id"), str) or not row[
        "parent_call_id"
    ].strip():
        errors.append(f"{prefix}: accepted result requires parent_call_id")
    safety = row.get("safety_enforcement")
    if safety not in SAFETY_ENFORCEMENT:
        errors.append(
            f"{prefix}: safety_enforcement must be one of "
            f"{sorted(SAFETY_ENFORCEMENT)}"
        )
    elif safety == "unknown":
        errors.append(f"{prefix}: accepted result cannot use unknown safety enforcement")
    return errors


def _validate_tree_ledger(ledger: dict[str, Any], *, project: bool = False, configured_cap: int | None = None) -> tuple[list[str], list[str]]:
    """Validate the v2 machine-readable root/coordinator/leaf tree contract.

    The v2 format intentionally keeps the row list compatible with v1 (``assignments``)
    while accepting ``tree.attempts``/``attempts`` as aliases.  Unknown or missing
    provenance is rejected rather than inferred from task names or paths.
    """
    errors: list[str] = []
    warnings: list[str] = []
    prefix = "project ledger" if project else "research ledger"
    tree = ledger.get("tree") if isinstance(ledger.get("tree"), dict) else ledger
    tree_id, run_id = tree.get("tree_id"), tree.get("run_id")
    for key, value in (("tree_id", tree_id), ("run_id", run_id)):
        try:
            uuid.UUID(str(value))
        except (ValueError, TypeError):
            errors.append(f"{prefix}.{key} must be a UUID")
    budget = tree.get("attempt_budget_N", tree.get("N"))
    cap = tree.get("concurrency_cap_C", tree.get("C"))
    wave_width = tree.get("wave_width_W", tree.get("W"))
    reserve = tree.get("verifier_reserve_V", tree.get("verifier_reserve", 0))
    for key, value in (
        ("attempt_budget_N", budget),
        ("concurrency_cap_C", cap),
        ("wave_width_W", wave_width),
        ("verifier_reserve_V", reserve),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{prefix}.{key} must be a non-negative integer")
    exceptional = tree.get("exceptional_budget") is True or tree.get("exceptional") is True
    max_budget = 64 if exceptional else 32
    if isinstance(budget, int) and (budget < 4 or budget > max_budget):
        errors.append(
            f"{prefix}.attempt_budget_N must be from 4 through {max_budget}"
        )
    if isinstance(cap, int) and cap < 1:
        errors.append(f"{prefix}.concurrency_cap_C must be positive")
    if isinstance(wave_width, int) and wave_width < 1:
        errors.append(f"{prefix}.wave_width_W must be positive")
    if isinstance(wave_width, int) and isinstance(cap, int) and wave_width > cap:
        errors.append(
            f"{prefix}.wave_width_W W={wave_width} exceeds concurrency cap C={cap}"
        )
    if isinstance(wave_width, int) and isinstance(budget, int) and wave_width > budget:
        errors.append(
            f"{prefix}.wave_width_W W={wave_width} exceeds attempt budget N={budget}"
        )
    if isinstance(cap, int) and configured_cap is not None and cap > configured_cap:
        errors.append(f"{prefix}.concurrency_cap_C C={cap} exceeds configured cap={configured_cap}")
    elif isinstance(cap, int) and configured_cap is None:
        warnings.append(f"{prefix}.concurrency_cap_C requires live configured-cap proof")
    if tree.get("max_workflow_depth") != 2:
        errors.append(f"{prefix}.max_workflow_depth must be 2")
    rows = tree.get("attempts", tree.get("assignments", ledger.get("attempts", ledger.get("assignments"))))
    if not isinstance(rows, list):
        errors.append(f"{prefix}.attempts/assignments must be an array")
        return errors, warnings
    if isinstance(budget, int) and len(rows) > budget:
        errors.append(
            f"{prefix} plans {len(rows)} attempts, exceeding attempt_budget_N={budget}"
        )
    ids: dict[str, dict[str, Any]] = {}
    order: dict[str, int] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"tree attempts[{i}] must be an object"); continue
        aid = row.get("attempt_id")
        if not isinstance(aid, str) or not aid.strip():
            errors.append(f"tree attempts[{i}].attempt_id is required"); continue
        if aid in ids: errors.append(f"duplicate attempt_id {aid!r}")
        ids[aid] = row; order[aid] = i
    children: dict[str, list[str]] = {aid: [] for aid in ids}
    edge_owners: dict[tuple[str, str], str] = {}
    started = 0
    started_rows: list[dict[str, Any]] = []
    intervals: list[tuple[datetime, datetime | None, str]] = []
    attempts_by_wave: dict[int, int] = {}
    research_quota_cells: dict[str, set[str]] = {
        "primary": set(),
        "adversarial": set(),
        "measurement_gap": set(),
    }
    research_coverage_owners: dict[str, str] = {}
    research_priority_groups: dict[str, list[dict[str, Any]]] = {}
    tree_overall_deadline = _parse_timestamp(
        tree.get("overall_deadline", ledger.get("overall_deadline"))
    )
    research_overall_deadline = tree_overall_deadline if not project else None
    if not project and research_overall_deadline is None:
        errors.append(
            "research ledger.overall_deadline must be a timezone ISO timestamp"
        )
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("attempt_id"), str): continue
        aid = row["attempt_id"]; pfx = f"tree attempts[{i}]"
        depth = row.get("depth")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0 or depth > 2:
            errors.append(f"{pfx}.depth must be 0..2")
        parent = row.get("parent_attempt_id")
        if parent is not None:
            if parent not in ids: errors.append(f"{pfx}.parent_attempt_id does not exist")
            elif order[parent] >= order[aid]: errors.append(f"{pfx}.parent must precede child")
            else:
                children.setdefault(parent, []).append(aid)
                if isinstance(depth, int) and depth != ids[parent].get("depth", -99) + 1:
                    errors.append(f"{pfx}.depth must equal parent depth + 1")
        if parent == aid: errors.append(f"{pfx}: self-cycle")
        # delegated_by must identify the exact parent spawn call, never task_name/path.
        delegated = row.get("delegated_by")
        if not isinstance(delegated, dict): delegated = {}
        edge_parent = delegated.get("parent_attempt_id", parent)
        if parent is not None and edge_parent != parent: errors.append(f"{pfx}.delegated_by parent mismatch")
        for edge_key in ("parent_thread_uuid", "parent_call_id"):
            if not isinstance(delegated.get(edge_key), str) or not delegated[edge_key].strip(): errors.append(f"{pfx}.delegated_by.{edge_key} is required")
        try: uuid.UUID(str(delegated.get("parent_thread_uuid")))
        except (ValueError, TypeError): errors.append(f"{pfx}.delegated_by.parent_thread_uuid must be UUID")
        edge_thread = delegated.get("parent_thread_uuid")
        edge_call = delegated.get("parent_call_id")
        if isinstance(edge_thread, str) and isinstance(edge_call, str) and edge_call:
            edge_key = (edge_thread, edge_call)
            previous_edge = edge_owners.get(edge_key)
            if previous_edge is not None and previous_edge != aid:
                errors.append(
                    f"{pfx}: delegated edge already belongs to {previous_edge!r}"
                )
            else:
                edge_owners[edge_key] = aid
        if parent is None:
            root_thread = row.get("root_parent_thread_uuid")
            root_call = row.get("root_parent_call_id")
            try:
                uuid.UUID(str(root_thread))
            except (ValueError, TypeError):
                errors.append(f"{pfx}.root_parent_thread_uuid must be UUID")
            if not isinstance(root_call, str) or not root_call.strip():
                errors.append(f"{pfx}.root_parent_call_id is required")
            if root_thread != edge_thread or root_call != edge_call:
                errors.append(f"{pfx}: root parent edge must match delegated_by")
        if parent is not None and parent in ids:
            expected_thread = ids[parent].get("child_thread_uuid") or ids[parent].get("thread_uuid")
            if expected_thread is not None and delegated.get("parent_thread_uuid") != expected_thread: errors.append(f"{pfx}: parent thread UUID mismatch")
        status = row.get("execution_status", row.get("state"))
        if status not in EXECUTION_STATES:
            errors.append(f"{pfx}.execution_status is invalid: {status!r}")
        else:
            if status in {"started", "completed", "failed", "timed_out", "abandoned"}:
                started += 1; started_rows.append(row)
        wave = row.get("wave")
        if not isinstance(wave, int) or isinstance(wave, bool) or wave < 1:
            errors.append(f"{pfx}.wave must be a positive integer")
        else:
            attempts_by_wave[wave] = attempts_by_wave.get(wave, 0) + 1
        if status not in {"planned", "not_dispatched"} and _parse_timestamp(row.get("started_at")) is None: errors.append(f"{pfx}.started_at must be timezone ISO timestamp")
        end = _parse_timestamp(row.get("finished_at")) or _parse_timestamp(row.get("timeout_at"))
        start = _parse_timestamp(row.get("started_at"))
        if status in {"completed", "failed", "timed_out", "abandoned", "not_dispatched"} and end is None:
            errors.append(f"{pfx}: terminal row requires finished_at or timeout_at")
        if status == "started" and end is not None:
            errors.append(f"{pfx}: started row cannot have a terminal timestamp")
        if status == "started" and start:
            intervals.append((start, None, aid))
        elif start and end:
            if end < start: errors.append(f"{pfx}: end precedes start")
            intervals.append((start, end, aid))
        role = row.get("role", row.get("kind"))
        kind = row.get("kind")
        if not isinstance(role, str) or not role.strip(): errors.append(f"{pfx}.role is required")
        coordinator_roles = {"coordinator", "research_coordinator", "luna_project_coordinator"}
        is_coord = role in coordinator_roles or kind == "coordinator"
        if is_coord and depth != 1: errors.append(f"{pfx}: coordinator must be depth 1")
        if is_coord:
            if not isinstance(row.get("descendant_budget"), int) or isinstance(row.get("descendant_budget"), bool) or row.get("descendant_budget", -1) < 0: errors.append(f"{pfx}.descendant_budget must be a non-negative integer")
            if not isinstance(row.get("planned_child_attempt_ids"), list): errors.append(f"{pfx}.planned_child_attempt_ids is required")
            if not isinstance(row.get("collected_result_ids"), list): errors.append(f"{pfx}.collected_result_ids is required")
        leaf_roles = {"research_scout_luna", "leaf", "builder", "luna_builder", "evidence_lane", "reviewer", "luna_reviewer", "verifier", "operator"}
        if role in leaf_roles and depth not in {1, 2}: errors.append(f"{pfx}: leaf role has invalid depth")
        if role in leaf_roles and children.get(aid): errors.append(f"{pfx}: leaf role may not spawn descendants")
        if row.get("may_spawn_descendants") is True and role in leaf_roles: errors.append(f"{pfx}: leaf may_spawn_descendants must be false")
        if row.get("retry_of") is not None and row.get("retry_of") not in ids:
            errors.append(f"{pfx}.retry_of must reference an earlier attempt")
        if row.get("retry_of") == aid: errors.append(f"{pfx}.retry_of creates a cycle")
        retry_of = row.get("retry_of")
        if retry_of is not None and retry_of in ids:
            prior = ids[retry_of]
            if order.get(retry_of, i) >= i: errors.append(f"{pfx}.retry_of must precede retry")
            if row.get("cell_id") is not None and prior.get("cell_id") != row.get("cell_id"):
                errors.append(f"{pfx}: retry must keep same cell_id")
            if row.get("owner") is not None and prior.get("owner") != row.get("owner"):
                errors.append(f"{pfx}: retry must keep same owner")
            if isinstance(row.get("attempt_ordinal"), int) and isinstance(prior.get("attempt_ordinal"), int):
                if row["attempt_ordinal"] != prior["attempt_ordinal"] + 1:
                    errors.append(f"{pfx}: retry attempt_ordinal must be consecutive")
            if not isinstance(row.get("retry_owner"), str) or not row["retry_owner"].strip():
                errors.append(f"{pfx}: retry_owner is required for retries")
            elif isinstance(prior.get("retry_owner"), str) and row["retry_owner"] != prior["retry_owner"]:
                errors.append(f"{pfx}: retry must keep the same retry_owner")
        allowed_accept = {"planned": {"pending"}, "not_dispatched": {"excluded"}, "started": {"pending"}, "completed": {"accepted", "rejected"}, "failed": {"excluded"}, "timed_out": {"excluded"}, "abandoned": {"excluded"}}
        acceptance = row.get("acceptance_status", "pending")
        if status in allowed_accept and acceptance not in allowed_accept[status]: errors.append(f"{pfx}: invalid state transition {status}->{acceptance}")
        if acceptance == "accepted" and (
            row.get("runtime_verified") is not True
            or not _canonical_uuid(row.get("thread_uuid"))
            or not _canonical_uuid(row.get("runtime_turn"))
        ):
            errors.append(f"{pfx}: accepted row requires strict runtime fields")
        if status in {"timed_out", "abandoned"} and acceptance == "accepted": errors.append(f"{pfx}: late completion after timeout cannot be accepted")
        if row.get("hidden_spawn") or row.get("spawn_agent_calls"):
            if role in leaf_roles: errors.append(f"{pfx}: leaf rollout contains spawn_agent call")
        if row.get("access_mode") == "root_only" and status not in {"planned", "not_dispatched"}: errors.append(f"{pfx}: root_only rows cannot run")
        if row.get("source_plane") in {"connector_private", "provider"} and row.get("access_mode") != "root_only": errors.append(f"{pfx}: private/provider must remain root_only")
        if not project and not is_coord:
            if kind not in {"evidence_lane", "verifier", "contradiction"}:
                errors.append(
                    f"{pfx}.kind must be evidence_lane, verifier, or contradiction "
                    "for EVIDENCE_LANE_ONLY research"
                )
            required_research_strings = (
                "coverage_cell",
                "source_universe",
                "exclusion_rule",
                "overlap_key",
            )
            for key in required_research_strings:
                value = row.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{pfx}.{key} must be a non-empty string")
            priority = row.get("priority")
            if not isinstance(priority, bool):
                errors.append(f"{pfx}.priority must be a boolean")
            quota = row.get("quota_label")
            if quota not in QUOTA_LABELS:
                errors.append(
                    f"{pfx}.quota_label must be one of {sorted(QUOTA_LABELS)}"
                )
            plane = row.get("source_plane")
            access_mode = row.get("access_mode")
            if plane not in SOURCE_PLANES:
                errors.append(
                    f"{pfx}.source_plane must be one of {sorted(SOURCE_PLANES)}"
                )
            if access_mode not in ACCESS_MODES:
                errors.append(
                    f"{pfx}.access_mode must be one of {sorted(ACCESS_MODES)}"
                )
            errors.extend(
                _access_errors(
                    pfx,
                    plane,
                    access_mode,
                    status,
                    acceptance,
                    row.get("safety_enforcement"),
                    row.get("runtime_verified"),
                    row.get("thread_uuid"),
                    row.get("gap_reason"),
                )
            )
            deadline = _parse_timestamp(row.get("deadline"))
            if deadline is None:
                errors.append(f"{pfx}.deadline must be a timezone ISO timestamp")
            elif (
                research_overall_deadline is not None
                and deadline > research_overall_deadline
            ):
                errors.append(f"{pfx}.deadline exceeds overall_deadline")
            errors.extend(
                _deadline_errors(
                    pfx,
                    status,
                    acceptance,
                    start,
                    end,
                    deadline,
                    research_overall_deadline,
                )
            )
            coverage_cell = row.get("coverage_cell")
            coverage_key = (
                " ".join(coverage_cell.split()).casefold()
                if isinstance(coverage_cell, str)
                else ""
            )
            if coverage_key:
                previous = research_coverage_owners.get(coverage_key)
                if previous is None:
                    research_coverage_owners[coverage_key] = aid
                elif row.get("retry_of") != previous:
                    errors.append(
                        f"coverage_cell {coverage_cell!r} is duplicated by {aid!r} "
                        f"without retry_of={previous!r}"
                    )
                if quota in research_quota_cells:
                    research_quota_cells[quota].add(coverage_key)
            overlap_key = row.get("overlap_key")
            if priority is True and isinstance(overlap_key, str) and overlap_key:
                research_priority_groups.setdefault(overlap_key, []).append(row)
        elif project and not is_coord:
            deadline = _parse_timestamp(row.get("deadline"))
            if deadline is None:
                errors.append(f"{pfx}.deadline must be a timezone ISO timestamp")
            elif tree_overall_deadline is not None and deadline > tree_overall_deadline:
                errors.append(f"{pfx}.deadline exceeds overall_deadline")
            errors.extend(
                _deadline_errors(
                    pfx,
                    status,
                    acceptance,
                    start,
                    end,
                    deadline,
                    tree_overall_deadline,
                )
            )
        elif is_coord:
            errors.extend(
                _deadline_errors(
                    pfx,
                    status,
                    acceptance,
                    start,
                    end,
                    None,
                    tree_overall_deadline,
                )
            )
    if isinstance(budget, int) and started > budget: errors.append(f"started attempts {started} exceed attempt_budget_N={budget}")
    if isinstance(wave_width, int):
        for wave, count in sorted(attempts_by_wave.items()):
            if count > wave_width:
                errors.append(
                    f"wave {wave} plans/starts {count} attempts, "
                    f"exceeding wave_width_W={wave_width}"
                )
    retry_limit = tree.get("retry_limit", 1)
    if not isinstance(retry_limit, int) or isinstance(retry_limit, bool) or retry_limit < 0:
        errors.append(f"{prefix}.retry_limit must be a non-negative integer")
    else:
        retries_by_root: dict[str, int] = {}
        for aid, row in ids.items():
            retry_of = row.get("retry_of")
            if retry_of is None or retry_of not in ids:
                continue
            root_retry = retry_of
            visited: set[str] = {aid}
            while root_retry in ids and ids[root_retry].get("retry_of") is not None:
                if root_retry in visited:
                    break
                visited.add(root_retry)
                root_retry = ids[root_retry]["retry_of"]
            retries_by_root[root_retry] = retries_by_root.get(root_retry, 0) + 1
        for root_retry, count in retries_by_root.items():
            if count > retry_limit:
                errors.append(
                    f"{prefix}: retry chain rooted at {root_retry!r} uses {count}, "
                    f"exceeding retry_limit={retry_limit}"
                )
    # Reserve lanes are never consumed by ordinary work.  A reserve is mandatory
    # for N>=4 and must be represented by planned verifier/contradiction rows.
    if isinstance(budget, int) and isinstance(reserve, int):
        if reserve < 0 or reserve >= budget:
            errors.append(f"{prefix}.verifier_reserve_V must satisfy 0 <= V < N")
        if budget >= 4:
            required_reserve = max(1, math.ceil(0.15 * budget))
            if reserve != required_reserve:
                errors.append(
                    f"{prefix}.verifier_reserve_V V={reserve} must equal "
                    f"max(1,ceil(.15*N))={required_reserve}"
                )
        reserve_rows = [r for r in rows if isinstance(r, dict) and (r.get("kind") in {"verifier", "contradiction"} or r.get("role") in {"verifier", "contradiction", "reviewer"})]
        if len(reserve_rows) < reserve:
            errors.append(f"{prefix}: verifier/contradiction planned rows {len(reserve_rows)} < reserve V={reserve}")
        nonreserve = [r for r in rows if isinstance(r, dict) and not (r.get("kind") in {"verifier", "contradiction"} or r.get("role") in {"verifier", "contradiction", "reviewer"})]
        if len(nonreserve) > budget - reserve:
            errors.append(f"{prefix}: non-reserve attempts {len(nonreserve)} exceed N-V={budget-reserve}")
        accepted_reserve = sum(1 for r in rows if r.get("acceptance_status") == "accepted" and (r.get("kind") in {"verifier", "contradiction"} or r.get("role") in {"verifier", "contradiction", "reviewer"}))
        phase = tree.get("phase", ledger.get("phase"))
        if phase in {"closure", "synthesis"} and accepted_reserve < reserve and tree.get("closure_status", ledger.get("closure_status")) != "blocked":
            errors.append(f"{prefix}: closure requires accepted verifier/contradiction >= V or explicit blocked gap")
        if tree.get("closure_status", ledger.get("closure_status")) == "complete" and accepted_reserve < reserve:
            errors.append(f"{prefix}: complete closure requires accepted verifier reserve")
    if not project and isinstance(budget, int):
        required_quota = math.ceil(0.20 * budget)
        for quota in ("primary", "adversarial"):
            actual = len(research_quota_cells[quota])
            if actual < required_quota:
                errors.append(
                    f"research ledger: unique {quota} coverage cells {actual} "
                    f"< ceil(20% of N)={required_quota}"
                )
        if len(research_quota_cells["measurement_gap"]) < 1:
            errors.append(
                "research ledger requires at least one measurement_gap coverage cell"
            )
    # cycle detection and interval sweep (all descendants, coordinators included)
    for aid in ids:
        seen: set[str] = set(); cur = aid
        while cur in ids and ids[cur].get("parent_attempt_id") is not None:
            cur = ids[cur].get("parent_attempt_id")
            if cur in seen: errors.append(f"cycle detected at {aid!r}"); break
            seen.add(cur)
    if isinstance(cap, int):
        points = sorted(
            {s for s, _, _ in intervals}
            | {e for _, e, _ in intervals if e is not None}
        )
        for t in points:
            active = sum(
                s <= t and (e is None or t < e) and ids[aid].get("role") != "root"
                for s, e, aid in intervals
            )
            if active > cap: errors.append(f"concurrency cap C={cap} exceeded ({active})")
    # Coordinator closure: exact planned children, all terminal and collected, no extras.
    for aid, row in ids.items():
        if row.get("role") not in {"coordinator", "research_coordinator", "luna_project_coordinator"} and row.get("kind") != "coordinator": continue
        planned = row.get("planned_child_attempt_ids", []); collected = row.get("collected_result_ids", [])
        if isinstance(planned, list) and isinstance(collected, list):
            if len(planned) != len(set(planned)):
                errors.append(f"coordinator {aid}: planned child list contains duplicates")
            if len(collected) != len(set(collected)):
                errors.append(f"coordinator {aid}: collected result list contains duplicates")
            actual = set(children.get(aid, []))
            if set(planned) != actual: errors.append(f"coordinator {aid}: planned child list mismatch")
            if set(collected) != actual: errors.append(f"coordinator {aid}: collected result list mismatch")
            for field in ("collection_uuid", "collection_call_id"):
                if field in row and (not isinstance(row.get(field), str) or not row[field].strip()):
                    errors.append(f"coordinator {aid}: {field} must be non-empty")
            if "collection_uuid" in row:
                try: uuid.UUID(str(row["collection_uuid"]))
                except (ValueError, TypeError): errors.append(f"coordinator {aid}: collection_uuid must be UUID")
            if "collection_receipt" in row and (not isinstance(row.get("collection_receipt"), str) or not row["collection_receipt"].strip()):
                errors.append(f"coordinator {aid}: collection_receipt must be non-empty")
            if any(ids[x].get("execution_status") not in {"completed", "failed", "timed_out", "abandoned", "not_dispatched"} for x in actual): errors.append(f"coordinator {aid}: child is not terminal")
            budget_c = row.get("descendant_budget")
            if isinstance(budget_c, int) and len(planned) > budget_c: errors.append(f"coordinator {aid}: descendant budget exceeded")
            if row.get("execution_status") == "completed":
                done = [_parse_timestamp(ids[x].get("finished_at")) or _parse_timestamp(ids[x].get("timeout_at")) for x in planned if x in ids]
                completed_times = [value for value in done if value is not None]
                finish = _parse_timestamp(row.get("finished_at"))
                if finish and (not all(done) or any(finish < d for d in done if d)): errors.append(f"coordinator {aid}: completed before child collection")
                if finish and completed_times and finish < max(completed_times): errors.append(f"coordinator {aid}: finished_at precedes collection completion")
                if row.get("acceptance_status") == "accepted" and (
                    not isinstance(row.get("collection_receipt"), str)
                    or not row["collection_receipt"].strip()
                ):
                    errors.append(
                        f"coordinator {aid}: accepted completion requires collection_receipt"
                    )
    # Research lifecycle is separate from the project integration lifecycle.
    if not project:
        phase = tree.get("phase", ledger.get("phase"))
        closure_status = tree.get("closure_status", ledger.get("closure_status"))
        if phase not in {"planning", "synthesis"}:
            errors.append(f"research ledger.phase must be planning or synthesis, got {phase!r}")
        if closure_status not in {"open", "blocked", "complete"}:
            errors.append(
                "research ledger.closure_status must be open, blocked, or complete"
            )
        if phase != "synthesis" and closure_status != "open":
            errors.append(
                "research ledger cannot be blocked/complete before synthesis phase"
            )
        if phase == "synthesis":
            unfinished = [
                aid
                for aid, row in ids.items()
                if row.get("execution_status") in {"planned", "started"}
            ]
            if unfinished:
                errors.append(
                    "research synthesis cannot contain planned/started attempts: "
                    + ", ".join(sorted(unfinished))
                )
            for overlap_key, priority_rows in research_priority_groups.items():
                covered = any(
                    row.get("acceptance_status") == "accepted"
                    for row in priority_rows
                )
                explicit_gap = any(
                    isinstance(row.get("gap_reason"), str)
                    and row["gap_reason"].strip()
                    for row in priority_rows
                )
                if not covered and not explicit_gap:
                    errors.append(
                        f"priority cell {overlap_key!r} is neither accepted nor "
                        "assigned a gap reason"
                    )

    # Project-specific dependency closure.
    if project:
        role_kinds = {
            "coordinator": {"coordinator", "luna_project_coordinator"},
            "builder": {"builder", "luna_builder", "default"},
            "reviewer": {"reviewer", "luna_reviewer", "verifier"},
            "verifier": {"reviewer", "luna_reviewer", "verifier"},
            "evidence_lane": {"evidence_lane", "research_scout_luna"},
        }
        for aid, row in ids.items():
            kind = row.get("kind", row.get("role")); role = row.get("role")
            if kind in role_kinds and role not in role_kinds[kind]:
                errors.append(f"project {aid}: role {role!r} incompatible with kind {kind!r}")
            dependencies = row.get("dependencies") or []
            if not isinstance(dependencies, list):
                continue
            row_start = _parse_timestamp(row.get("started_at"))
            if row.get("execution_status") == "planned" or row_start is None:
                continue
            for dependency_id in dependencies:
                dependency = ids.get(dependency_id)
                if dependency is None:
                    continue
                dependency_end = (
                    _parse_timestamp(dependency.get("finished_at"))
                    or _parse_timestamp(dependency.get("timeout_at"))
                )
                if dependency.get("execution_status") not in {
                    "completed", "failed", "timed_out", "abandoned"
                } or dependency_end is None:
                    errors.append(
                        f"project {aid}: dependency {dependency_id!r} was not terminal before start"
                    )
                elif row_start < dependency_end:
                    errors.append(
                        f"project {aid}: started before dependency {dependency_id!r} finished"
                    )
        builders = [
            aid
            for aid, r in ids.items()
            if r.get("kind", r.get("role")) == "builder"
            and r.get("acceptance_status") == "accepted"
        ]
        reviewers = [r for r in ids.values() if r.get("kind", r.get("role")) in {"reviewer", "verifier"}]
        for aid in builders:
            if not any(
                aid in (r.get("dependencies") or [])
                and r.get("acceptance_status") == "accepted"
                and order.get(r.get("attempt_id"), -1) > order.get(aid, -1)
                for r in reviewers
            ):
                errors.append(f"builder {aid} lacks a subsequent accepted reviewer/verifier dependency")
    if not errors: print(f"OK: {prefix} v2 tree={tree_id}, attempts={len(rows)}, started={started}")
    return errors, warnings


def _validate_project_v2_contract(ledger: dict[str, Any]) -> list[str]:
    """Validate project-only integration and evidence-gate closure for v2."""
    errors: list[str] = []
    phase = ledger.get("phase")
    closure_status = ledger.get("closure_status")
    if phase not in {"planning", "integration", "closure"}:
        errors.append(
            "project ledger.phase must be planning, integration, or closure"
        )
    if closure_status not in {"open", "blocked", "complete"}:
        errors.append(
            "project ledger.closure_status must be open, blocked, or complete"
        )
    if phase != "closure" and closure_status != "open":
        errors.append("project ledger cannot be blocked/complete before closure phase")

    root_integration = ledger.get("root_integration_status")
    if root_integration not in ROOT_INTEGRATION_STATES:
        errors.append(
            "project ledger.root_integration_status must be one of "
            f"{sorted(ROOT_INTEGRATION_STATES)}"
        )
    root_receipt = ledger.get("root_integration_receipt")
    if root_receipt is not None and (
        not isinstance(root_receipt, str) or not root_receipt.strip()
    ):
        errors.append(
            "project ledger.root_integration_receipt must be null or a non-empty string"
        )
    if _parse_timestamp(ledger.get("overall_deadline")) is None:
        errors.append(
            "project ledger.overall_deadline must be an ISO-8601 timestamp with timezone"
        )
    errors.extend(_validate_project_gates(ledger))

    assignments = ledger.get("assignments")
    if not isinstance(assignments, list):
        return [*errors, "project ledger.assignments must be an array"]
    order = {
        row.get("attempt_id"): index
        for index, row in enumerate(assignments)
        if isinstance(row, dict) and isinstance(row.get("attempt_id"), str)
    }
    accepted_by_id = {
        row.get("attempt_id"): row.get("acceptance_status") == "accepted"
        for row in assignments
        if isinstance(row, dict) and isinstance(row.get("attempt_id"), str)
    }
    ownership_owners: dict[str, str] = {}
    for index, row in enumerate(assignments):
        if not isinstance(row, dict):
            continue
        pfx = f"tree attempts[{index}]"
        kind = row.get("kind")
        if kind not in PROJECT_KINDS:
            errors.append(f"{pfx}.kind must be one of {sorted(PROJECT_KINDS)}")
        dependencies = row.get("dependencies", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(value, str) for value in dependencies
        ):
            errors.append(f"{pfx}.dependencies must be an array of attempt IDs")
            dependencies = []
        for dependency in dependencies:
            if dependency not in order or order[dependency] >= index:
                errors.append(f"{pfx}.dependency {dependency!r} must be earlier")
            if row.get("acceptance_status") == "accepted" and not accepted_by_id.get(
                dependency, False
            ):
                errors.append(
                    f"{pfx}: accepted result depends on non-accepted {dependency!r}"
                )
        integration = row.get("integration_status")
        if integration not in INTEGRATION_STATES:
            errors.append(
                f"{pfx}.integration_status must be one of {sorted(INTEGRATION_STATES)}"
            )
        if kind in {"builder", "operator"} and row.get("acceptance_status") == "accepted":
            ownership = row.get("ownership")
            if not isinstance(ownership, list) or not ownership:
                errors.append(f"{pfx}.ownership must be a non-empty array")
                ownership = []
            for raw_owner in ownership:
                if not isinstance(raw_owner, str) or not raw_owner.strip():
                    errors.append(f"{pfx}.ownership values must be non-empty strings")
                    continue
                owner = raw_owner.strip().casefold()
                if owner == "read-only":
                    continue
                previous = ownership_owners.get(owner)
                if previous is not None:
                    errors.append(
                        f"ownership {raw_owner!r} is shared by accepted attempts "
                        f"{previous!r} and {row.get('attempt_id')!r}"
                    )
                else:
                    ownership_owners[owner] = str(row.get("attempt_id"))
            if closure_status == "complete" and integration != "integrated":
                errors.append(
                    f"{pfx}: accepted {kind} must be integrated before complete closure"
                )

    if phase == "closure":
        live = [
            row
            for row in assignments
            if isinstance(row, dict)
            and row.get("execution_status") in {"planned", "started"}
        ]
        if live:
            errors.append(f"project closure has {len(live)} unfinished assignment(s)")
        if closure_status == "complete":
            if root_integration != "completed" or not isinstance(root_receipt, str) or not root_receipt.strip():
                errors.append(
                    "complete project closure requires completed root integration "
                    "and a receipt locator"
                )
            target = ledger.get("target_gate")
            verified = ledger.get("verified_gates")
            if isinstance(verified, list) and target not in verified:
                errors.append(
                    f"complete project closure has not verified target_gate {target!r}"
                )
    return errors


def validate_research_ledger(
    path: Path, configured_cap: int | None = None
) -> tuple[list[str], list[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            ledger = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read research ledger JSON {path}: {exc}"], []

    if not isinstance(ledger, dict):
        return ["research ledger must be a JSON object"], []

    errors: list[str] = []
    warnings: list[str] = []
    if ledger.get("ledger_type", "research") != "research":
        errors.append("research ledger.ledger_type must be 'research' when present")
    if ledger.get("version") == 2:
        return _validate_tree_ledger(
            ledger, project=False, configured_cap=configured_cap
        )
    if ledger.get("version") != 1:
        errors.append(f"ledger.version must be 1, got {ledger.get('version')!r}")
    phase = ledger.get("phase")
    if phase not in {"planning", "synthesis"}:
        errors.append(f"ledger.phase must be planning or synthesis, got {phase!r}")
    budget = ledger.get("N")
    if (
        not isinstance(budget, int)
        or isinstance(budget, bool)
        or budget < 3
        or budget > 20
    ):
        errors.append(f"ledger.N must be an integer from 3 through 20, got {budget!r}")
        budget = None
    overall_deadline = _parse_timestamp(ledger.get("overall_deadline"))
    if overall_deadline is None:
        errors.append("ledger.overall_deadline must be an ISO-8601 timestamp with timezone")

    assignments = ledger.get("assignments")
    if not isinstance(assignments, list):
        errors.append("ledger.assignments must be an array")
        return errors, warnings
    if budget is not None and len(assignments) > budget:
        errors.append(
            f"ledger plans {len(assignments)} attempts, exceeding assignment budget N={budget}"
        )

    required_strings = (
        "attempt_id",
        "coverage_cell",
        "source_universe",
        "exclusion_rule",
        "overlap_key",
    )
    seen_attempts: set[str] = set()
    attempt_order: list[str] = []
    retry_counts: dict[str, int] = {}
    quota_cells: dict[str, set[str]] = {
        "primary": set(),
        "adversarial": set(),
        "measurement_gap": set(),
    }
    priority_groups: dict[str, list[dict[str, Any]]] = {}
    coverage_owners: dict[str, str] = {}
    started_count = 0
    accepted_count = 0
    final_count = 0

    for index, raw in enumerate(assignments):
        prefix = f"assignments[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for key in required_strings:
            value = raw.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")

        attempt_id = raw.get("attempt_id")
        if isinstance(attempt_id, str) and attempt_id:
            if attempt_id in seen_attempts:
                errors.append(f"duplicate attempt_id {attempt_id!r}")
            seen_attempts.add(attempt_id)
            attempt_order.append(attempt_id)

        priority = raw.get("priority")
        if not isinstance(priority, bool):
            errors.append(f"{prefix}.priority must be a boolean")
        quota = raw.get("quota_label")
        if quota not in QUOTA_LABELS:
            errors.append(
                f"{prefix}.quota_label must be one of {sorted(QUOTA_LABELS)}, got {quota!r}"
            )
        plane = raw.get("source_plane")
        if plane not in SOURCE_PLANES:
            errors.append(
                f"{prefix}.source_plane must be one of {sorted(SOURCE_PLANES)}, got {plane!r}"
            )
        access_mode = raw.get("access_mode")
        if access_mode not in ACCESS_MODES:
            errors.append(
                f"{prefix}.access_mode must be one of {sorted(ACCESS_MODES)}, "
                f"got {access_mode!r}"
            )
        assignment_deadline = _parse_timestamp(raw.get("deadline"))
        if assignment_deadline is None:
            errors.append(f"{prefix}.deadline must be an ISO-8601 timestamp with timezone")
        elif overall_deadline is not None and assignment_deadline > overall_deadline:
            errors.append(f"{prefix}.deadline exceeds ledger.overall_deadline")

        execution = raw.get("execution_status")
        acceptance = raw.get("acceptance_status")
        if execution not in EXECUTION_STATES:
            errors.append(
                f"{prefix}.execution_status must be one of "
                f"{sorted(EXECUTION_STATES)}, got {execution!r}"
            )
        if acceptance not in ACCEPTANCE_STATES:
            errors.append(
                f"{prefix}.acceptance_status must be one of "
                f"{sorted(ACCEPTANCE_STATES)}, got {acceptance!r}"
            )
        errors.extend(_state_errors(prefix, execution, acceptance))

        runtime_verified = raw.get("runtime_verified")
        if not isinstance(runtime_verified, bool):
            errors.append(f"{prefix}.runtime_verified must be a boolean")
        thread_uuid = raw.get("thread_uuid")
        if thread_uuid is not None:
            if not _canonical_uuid(thread_uuid):
                errors.append(f"{prefix}.thread_uuid is not a UUID: {thread_uuid!r}")

        retry_of = raw.get("retry_of")
        if retry_of is not None:
            if not isinstance(retry_of, str) or retry_of not in seen_attempts:
                errors.append(
                    f"{prefix}.retry_of must reference an earlier attempt_id, got {retry_of!r}"
                )
            else:
                retry_counts[retry_of] = retry_counts.get(retry_of, 0) + 1
                if retry_counts[retry_of] > 1:
                    errors.append(f"attempt {retry_of!r} has more than one retry")

        if execution in {"started", "completed", "failed", "timed_out", "abandoned"}:
            started_count += 1
        if execution in {"completed", "failed", "timed_out", "abandoned", "not_dispatched"}:
            final_count += 1
        errors.extend(
            _access_errors(
                prefix,
                plane,
                access_mode,
                execution,
                acceptance,
                raw.get("safety_enforcement"),
                runtime_verified,
                thread_uuid,
                raw.get("gap_reason"),
            )
        )
        if acceptance == "accepted":
            accepted_count += 1
            errors.extend(_accepted_runtime_errors(prefix, raw))

        coverage_cell = raw.get("coverage_cell")
        coverage_key = (
            " ".join(coverage_cell.split()).casefold()
            if isinstance(coverage_cell, str)
            else ""
        )
        if coverage_key:
            owner = coverage_owners.get(coverage_key)
            if owner is None and isinstance(attempt_id, str):
                coverage_owners[coverage_key] = attempt_id
            elif owner is not None and raw.get("retry_of") != owner:
                errors.append(
                    f"coverage_cell {coverage_cell!r} is duplicated by "
                    f"{attempt_id!r} without retry_of={owner!r}"
                )
        overlap_key = raw.get("overlap_key")
        if isinstance(overlap_key, str) and overlap_key:
            if quota in quota_cells:
                quota_cells[quota].add(coverage_key)
            if priority is True:
                priority_groups.setdefault(overlap_key, []).append(raw)

    if budget is not None and started_count > budget:
        errors.append(f"started attempts {started_count} exceed N={budget}")
    if budget is not None:
        twenty_percent = (budget + 4) // 5
        required = {
            "primary": twenty_percent,
            "adversarial": twenty_percent,
            "measurement_gap": 1,
        }
        for label, minimum in required.items():
            actual = len(quota_cells[label])
            if actual < minimum:
                errors.append(
                    f"quota {label} requires {minimum} unique cell(s) for N={budget}, got {actual}"
                )

    overlap_owners: dict[str, str] = {}
    for raw in assignments:
        if not isinstance(raw, dict):
            continue
        key = raw.get("overlap_key")
        attempt_id = raw.get("attempt_id")
        if not isinstance(key, str) or not isinstance(attempt_id, str):
            continue
        owner = overlap_owners.get(key)
        if owner is None:
            overlap_owners[key] = attempt_id
        elif raw.get("retry_of") != owner:
            errors.append(
                f"overlap_key {key!r} is duplicated by {attempt_id!r} without retry_of={owner!r}"
            )

    if phase == "synthesis":
        in_flight = sum(
            1
            for raw in assignments
            if isinstance(raw, dict) and raw.get("execution_status") == "started"
        )
        if in_flight:
            errors.append(f"synthesis ledger has {in_flight} still-started assignment(s)")
        for key, rows in priority_groups.items():
            covered = any(row.get("acceptance_status") == "accepted" for row in rows)
            gapped = any(
                isinstance(row.get("gap_reason"), str)
                and bool(row["gap_reason"].strip())
                for row in rows
            )
            if not covered and not gapped:
                errors.append(
                    f"priority cell {key!r} is neither accepted nor assigned a gap reason"
                )

    if not errors:
        print(
            f"OK: ledger phase={phase}, N={budget}, planned={len(assignments)}, "
            f"started={started_count}, final={final_count}, accepted={accepted_count}"
        )
    return errors, warnings


def _validate_project_gates(ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    target = ledger.get("target_gate")
    if target not in VERIFIED_GATE_ORDER:
        errors.append(
            f"project ledger.target_gate must be one of {list(VERIFIED_GATE_ORDER)}, "
            f"got {target!r}"
        )
    verified = ledger.get("verified_gates")
    if not isinstance(verified, list) or any(
        gate not in VERIFIED_GATE_ORDER for gate in verified
    ):
        errors.append(
            "project ledger.verified_gates must be an ordered array of known gates"
        )
        verified = []
    elif verified != list(VERIFIED_GATE_ORDER[: len(verified)]):
        errors.append(
            "project ledger.verified_gates must be a contiguous prefix from LOCAL_PASS"
        )
    receipts = ledger.get("gate_receipts")
    if not isinstance(receipts, dict):
        errors.append("project ledger.gate_receipts must be an object")
        receipts = {}
    for gate in verified:
        value = receipts.get(gate)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"project ledger verified gate {gate} requires a receipt locator")
    if any(
        gate in verified for gate in ("PROVIDER_PASS", "PUBLIC_PASS", "HUMAN_GO")
    ) and ledger.get("external_authority") is not True:
        errors.append(
            "project ledger external gates require external_authority=true"
        )
    if ledger.get("external_authority") not in {True, False}:
        errors.append("project ledger.external_authority must be a boolean")
    return errors


def validate_project_ledger(path: Path, configured_cap: int | None = None) -> tuple[list[str], list[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            ledger = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read project ledger JSON {path}: {exc}"], []
    if not isinstance(ledger, dict):
        return ["project ledger must be a JSON object"], []

    errors: list[str] = []
    warnings: list[str] = []
    if ledger.get("ledger_type") != "project":
        errors.append("project ledger.ledger_type must be 'project'")
    if ledger.get("version") == 2:
        tree_errors, tree_warnings = _validate_tree_ledger(
            ledger, project=True, configured_cap=configured_cap
        )
        tree_errors.extend(_validate_project_v2_contract(ledger))
        return tree_errors, tree_warnings
    if ledger.get("version") != 1:
        errors.append(f"project ledger.version must be 1, got {ledger.get('version')!r}")
    phase = ledger.get("phase")
    if phase not in {"planning", "integration", "closure"}:
        errors.append(
            f"project ledger.phase must be planning, integration, or closure, got {phase!r}"
        )
    closure_status = ledger.get("closure_status")
    if closure_status not in {"open", "blocked", "complete"}:
        errors.append(
            "project ledger.closure_status must be open, blocked, or complete"
        )
    if phase != "closure" and closure_status != "open":
        errors.append("project ledger cannot be blocked/complete before closure phase")
    root_integration = ledger.get("root_integration_status")
    if root_integration not in ROOT_INTEGRATION_STATES:
        errors.append(
            "project ledger.root_integration_status must be one of "
            f"{sorted(ROOT_INTEGRATION_STATES)}"
        )
    root_receipt = ledger.get("root_integration_receipt")
    if root_receipt is not None and (
        not isinstance(root_receipt, str) or not root_receipt.strip()
    ):
        errors.append(
            "project ledger.root_integration_receipt must be null or a non-empty string"
        )

    budget = ledger.get("N")
    if (
        not isinstance(budget, int)
        or isinstance(budget, bool)
        or budget < 1
        or budget > 20
    ):
        errors.append(f"project ledger.N must be an integer from 1 through 20, got {budget!r}")
        budget = None
    reserve = ledger.get("verifier_reserve")
    if (
        not isinstance(reserve, int)
        or isinstance(reserve, bool)
        or reserve < 0
        or (budget is not None and reserve >= budget)
        or (budget is not None and budget >= 4 and reserve < 1)
    ):
        errors.append("project ledger.verifier_reserve must be from 1 through N")
        reserve = None
    overall_deadline = _parse_timestamp(ledger.get("overall_deadline"))
    if overall_deadline is None:
        errors.append(
            "project ledger.overall_deadline must be an ISO-8601 timestamp with timezone"
        )
    errors.extend(_validate_project_gates(ledger))

    assignments = ledger.get("assignments")
    if not isinstance(assignments, list):
        errors.append("project ledger.assignments must be an array")
        return errors, warnings
    if budget is not None and len(assignments) > budget:
        errors.append(
            f"project ledger plans {len(assignments)} attempts, exceeding N={budget}"
        )

    seen: set[str] = set()
    status_by_attempt: dict[str, str] = {}
    ownership_owners: dict[str, str] = {}
    started = 0
    final = 0
    accepted = 0
    verifier_rows = 0
    accepted_verifiers = 0
    for index, row in enumerate(assignments):
        prefix = f"assignments[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        attempt_id = row.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            errors.append(f"{prefix}.attempt_id must be a non-empty string")
            attempt_id = f"invalid-{index}"
        elif attempt_id in seen:
            errors.append(f"duplicate attempt_id {attempt_id!r}")
        seen.add(attempt_id)

        kind = row.get("kind")
        if kind not in PROJECT_KINDS:
            errors.append(
                f"{prefix}.kind must be one of {sorted(PROJECT_KINDS)}, got {kind!r}"
            )
        if kind == "verifier":
            verifier_rows += 1
        role = row.get("agent_role")
        role_allowed = {
            "coordinator": {"coordinator", "luna_project_coordinator"},
            "builder": {"builder", "luna_builder", "default"},
            "reviewer": {"reviewer", "luna_reviewer", "verifier"},
            "verifier": {"reviewer", "luna_reviewer", "verifier"},
            "evidence_lane": {"evidence_lane", "research_scout_luna"},
        }
        if kind in role_allowed and role is not None and role not in role_allowed[kind]:
            errors.append(f"{prefix}.agent_role {role!r} incompatible with kind {kind!r}")
        for key in ("objective", "evidence_locator"):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")

        ownership = row.get("ownership")
        if not isinstance(ownership, list) or not ownership or any(
            not isinstance(value, str) or not value.strip() for value in ownership
        ):
            errors.append(f"{prefix}.ownership must be a non-empty string array")
            ownership = []
        dependencies = row.get("dependencies")
        if not isinstance(dependencies, list) or any(
            not isinstance(value, str) for value in dependencies
        ):
            errors.append(f"{prefix}.dependencies must be an array of attempt IDs")
            dependencies = []
        for dependency in dependencies:
            if dependency not in status_by_attempt:
                errors.append(
                    f"{prefix}.dependencies must reference earlier attempts, got {dependency!r}"
                )

        criteria = row.get("acceptance_criteria")
        if not isinstance(criteria, list) or not criteria or any(
            not isinstance(value, str) or not value.strip() for value in criteria
        ):
            errors.append(
                f"{prefix}.acceptance_criteria must be a non-empty string array"
            )
        deadline = _parse_timestamp(row.get("deadline"))
        if deadline is None:
            errors.append(f"{prefix}.deadline must be an ISO-8601 timestamp with timezone")
        elif overall_deadline is not None and deadline > overall_deadline:
            errors.append(f"{prefix}.deadline exceeds project ledger.overall_deadline")

        execution = row.get("execution_status")
        acceptance = row.get("acceptance_status")
        if execution not in EXECUTION_STATES:
            errors.append(f"{prefix}.execution_status is invalid: {execution!r}")
        if acceptance not in ACCEPTANCE_STATES:
            errors.append(f"{prefix}.acceptance_status is invalid: {acceptance!r}")
        errors.extend(_state_errors(prefix, execution, acceptance))
        if execution in {"started", "completed", "failed", "timed_out", "abandoned"}:
            started += 1
        if execution in {"completed", "failed", "timed_out", "abandoned", "not_dispatched"}:
            final += 1
        if acceptance == "accepted":
            accepted += 1
            if kind == "verifier":
                accepted_verifiers += 1
            errors.extend(_accepted_runtime_errors(prefix, row))
            for dependency in dependencies:
                if status_by_attempt.get(dependency) != "accepted":
                    errors.append(
                        f"{prefix}: accepted result depends on non-accepted {dependency!r}"
                    )

        runtime_verified = row.get("runtime_verified")
        if not isinstance(runtime_verified, bool):
            errors.append(f"{prefix}.runtime_verified must be a boolean")
        thread_uuid = row.get("thread_uuid")
        if thread_uuid is not None:
            if not _canonical_uuid(thread_uuid):
                errors.append(f"{prefix}.thread_uuid is not a UUID: {thread_uuid!r}")

        if kind == "evidence_lane":
            plane = row.get("source_plane")
            access_mode = row.get("access_mode")
            if plane not in SOURCE_PLANES:
                errors.append(f"{prefix}.source_plane is invalid: {plane!r}")
            if access_mode not in ACCESS_MODES:
                errors.append(f"{prefix}.access_mode is invalid: {access_mode!r}")
            errors.extend(
                _access_errors(
                    prefix,
                    plane,
                    access_mode,
                    execution,
                    acceptance,
                    row.get("safety_enforcement"),
                    runtime_verified,
                    thread_uuid,
                    row.get("gap_reason"),
                )
            )

        integration = row.get("integration_status")
        if integration not in INTEGRATION_STATES:
            errors.append(
                f"{prefix}.integration_status must be one of "
                f"{sorted(INTEGRATION_STATES)}, got {integration!r}"
            )
        if kind in {"builder", "operator"} and acceptance == "accepted":
            for raw_owner in ownership:
                owner = raw_owner.strip().casefold()
                if owner == "read-only":
                    continue
                previous = ownership_owners.get(owner)
                if previous is not None:
                    errors.append(
                        f"ownership {raw_owner!r} is shared by accepted attempts "
                        f"{previous!r} and {attempt_id!r}"
                    )
                else:
                    ownership_owners[owner] = attempt_id
            if phase == "closure" and closure_status == "complete" and integration != "integrated":
                errors.append(
                    f"{prefix}: accepted {kind} must be integrated before complete closure"
                )
        status_by_attempt[attempt_id] = (
            acceptance if isinstance(acceptance, str) else "invalid"
        )

    if budget is not None and started > budget:
        errors.append(f"project started attempts {started} exceed N={budget}")
    if reserve is not None and verifier_rows < reserve:
        errors.append(
            f"project verifier reserve={reserve} but only {verifier_rows} verifier row(s) exist"
        )
    if budget is not None and reserve is not None:
        nonreserve_started = sum(1 for row in assignments if isinstance(row, dict) and row.get("execution_status") in {"started", "completed", "failed", "timed_out", "abandoned"} and row.get("kind") not in {"verifier", "contradiction"})
        if nonreserve_started > budget - reserve:
            errors.append(f"project non-reserve attempts {nonreserve_started} exceed N-V={budget-reserve}")
        if phase == "closure" and closure_status != "blocked" and accepted_verifiers < reserve:
            errors.append(f"project closure requires accepted verifier reserve={reserve} or blocked gap")
    if phase == "closure":
        still_started = sum(
            1
            for row in assignments
            if isinstance(row, dict) and row.get("execution_status") == "started"
        )
        if still_started:
            errors.append(f"project closure has {still_started} live assignment(s)")
        if closure_status == "complete":
            if root_integration != "completed" or not isinstance(root_receipt, str):
                errors.append(
                    "complete project closure requires completed root integration "
                    "and a receipt locator"
                )
            if any(
                isinstance(row, dict)
                and row.get("execution_status") in {"planned", "started"}
                for row in assignments
            ):
                errors.append("complete project closure cannot contain unfinished rows")
            if reserve is not None and accepted_verifiers < reserve:
                errors.append(
                    f"complete project closure requires {reserve} accepted verifier(s), "
                    f"got {accepted_verifiers}"
                )
            target = ledger.get("target_gate")
            verified = ledger.get("verified_gates")
            if isinstance(verified, list) and target not in verified:
                errors.append(
                    f"complete project closure has not verified target_gate {target!r}"
                )

    if not errors:
        print(
            f"OK: project ledger phase={phase}, closure={closure_status}, N={budget}, "
            f"planned={len(assignments)}, started={started}, final={final}, "
            f"accepted={accepted}, verifier_accepted={accepted_verifiers}"
        )
    return errors, warnings


def validate_assignment_ledger(path: Path, configured_cap: int | None = None) -> tuple[list[str], list[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            ledger = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read assignment ledger JSON {path}: {exc}"], []
    if not isinstance(ledger, dict):
        return ["assignment ledger must be a JSON object"], []
    if ledger.get("ledger_type", "research") == "project":
        return validate_project_ledger(path, configured_cap=configured_cap)
    return validate_research_ledger(path, configured_cap=configured_cap)


def validate_runtime_rollout(
    path: Path,
    role_name: str,
    require_read_only: bool = False,
    runtime_turn: str | None = None,
    allow_generic_worker: bool = False,
) -> tuple[list[str], list[str]]:
    latest_context: tuple[int, dict[str, Any]] | None = None
    contexts_by_turn: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    session_meta: dict[str, Any] | None = None
    completed_turns: dict[str, list[int]] = {}
    session_meta_count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    document = json.loads(line)
                except json.JSONDecodeError as exc:
                    return [f"invalid JSONL at {path}:{line_number}: {exc}"], []
                payload = document.get("payload")
                if document.get("type") == "session_meta" and isinstance(payload, dict):
                    session_meta_count += 1
                    if session_meta is None:
                        session_meta = payload
                if document.get("type") == "turn_context" and isinstance(payload, dict):
                    latest_context = (line_number, payload)
                    context_turn = payload.get("turn_id")
                    if isinstance(context_turn, str):
                        contexts_by_turn.setdefault(context_turn, []).append(
                            (line_number, payload)
                        )
                if (
                    document.get("type") == "event_msg"
                    and isinstance(payload, dict)
                    and payload.get("type") == "task_complete"
                    and isinstance(payload.get("turn_id"), str)
                ):
                    completed_turns.setdefault(payload["turn_id"], []).append(
                        line_number
                    )
    except OSError as exc:
        return [f"cannot read runtime rollout {path}: {exc}"], []

    errors: list[str] = []
    warnings: list[str] = []
    depth: object = None
    parent: object = None
    spawned_role: object = None
    agent_path: object = None
    if session_meta is None:
        errors.append(f"{path} contains no session_meta")
    else:
        if session_meta_count != 1:
            errors.append(
                f"{path} contains {session_meta_count} session_meta records; expected 1"
            )
        if session_meta.get("thread_source") != "subagent":
            errors.append("runtime rollout is not identified as a subagent thread")
        thread_id = session_meta.get("id")
        try:
            normalized_thread = str(uuid.UUID(str(thread_id)))
        except (ValueError, TypeError):
            errors.append(f"runtime session_meta id is not a UUID: {thread_id!r}")
        else:
            if str(thread_id) != normalized_thread:
                errors.append(
                    "runtime session_meta id must use canonical UUID form, "
                    f"got {thread_id!r}"
                )
        actual_role = session_meta.get("agent_role")
        if role_name == "worker" and not allow_generic_worker:
            errors.append("generic worker runtime requires --allow-generic-worker")
        if actual_role != role_name:
            errors.append(
                f"runtime agent role must be {role_name!r}, got {actual_role!r}"
            )
        depth, spawned_parent, spawned_role, agent_path = _spawn_metadata(session_meta)
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
            errors.append(f"runtime subagent depth must be a positive integer, got {depth!r}")
        parent_field = session_meta.get("parent_thread_id")
        if parent_field is not None and spawned_parent is not None and parent_field != spawned_parent:
            errors.append(
                "runtime parent_thread_id conflicts with source.thread_spawn: "
                f"{parent_field!r} != {spawned_parent!r}"
            )
        parent = parent_field or spawned_parent
        try:
            normalized_parent = str(uuid.UUID(str(parent)))
        except (ValueError, TypeError):
            errors.append(f"runtime parent thread is not a UUID: {parent!r}")
        else:
            if str(parent) != normalized_parent:
                errors.append(
                    f"runtime parent thread must use canonical UUID form, got {parent!r}"
                )
        if spawned_role != role_name:
            errors.append(
                "runtime source.thread_spawn agent_role must be "
                f"{role_name!r}, got {spawned_role!r}"
            )
        if not isinstance(agent_path, str) or not agent_path.strip():
            errors.append("runtime source.thread_spawn agent_path must be non-empty")

    selected_entry = latest_context
    if runtime_turn is not None:
        try:
            normalized_turn = str(uuid.UUID(runtime_turn))
        except ValueError:
            errors.append(f"runtime turn must be a UUID, got {runtime_turn!r}")
            normalized_turn = runtime_turn
        entries = contexts_by_turn.get(normalized_turn, [])
        if not entries:
            errors.append(f"runtime rollout contains no turn_context for {normalized_turn}")
            selected_entry = None
        elif len(entries) > 1:
            errors.append(
                f"runtime rollout contains {len(entries)} turn_context records for "
                f"{normalized_turn}; expected 1"
            )
            selected_entry = entries[-1]
        else:
            selected_entry = entries[0]

    if selected_entry is None:
        errors.append(f"{path} contains no turn_context runtime metadata")
        return errors, warnings
    selected_line, selected_context = selected_entry

    turn_id = selected_context.get("turn_id")
    try:
        normalized_selected_turn = str(uuid.UUID(str(turn_id)))
    except (ValueError, TypeError):
        errors.append(f"selected runtime turn is not a UUID: {turn_id!r}")
        normalized_selected_turn = str(turn_id)
    else:
        if str(turn_id) != normalized_selected_turn:
            errors.append(
                f"selected runtime turn must use canonical UUID form, got {turn_id!r}"
            )
    duplicate_contexts = contexts_by_turn.get(normalized_selected_turn, [])
    if len(duplicate_contexts) > 1:
        errors.append(
            f"runtime rollout contains {len(duplicate_contexts)} turn_context records "
            f"for selected turn {normalized_selected_turn}; expected 1"
        )
    completion_lines = completed_turns.get(normalized_selected_turn, [])
    if not completion_lines:
        errors.append(
            f"selected runtime turn {turn_id!r} has no matching task_complete receipt"
        )
    elif not any(line_number > selected_line for line_number in completion_lines):
        errors.append(
            f"selected runtime turn {turn_id!r} has no task_complete after its "
            "turn_context"
        )

    model = selected_context.get("model")
    effort = selected_context.get("effort")
    if model != EXPECTED_MODEL:
        errors.append(f"runtime model must be {EXPECTED_MODEL!r}, got {model!r}")
    if effort != EXPECTED_REASONING_EFFORT:
        errors.append(
            "runtime reasoning effort must be "
            f"{EXPECTED_REASONING_EFFORT!r}, got {effort!r}"
        )

    sandbox = _sandbox_name(selected_context)
    is_read_only = isinstance(sandbox, str) and sandbox.lower() in READ_ONLY_SANDBOXES
    if require_read_only and not is_read_only:
        errors.append(
            "effective runtime sandbox must be read-only for this lane, "
            f"got {sandbox!r}"
        )
    elif not is_read_only:
        warnings.append(
            f"effective runtime sandbox is {sandbox!r}; the no-mutation boundary "
            "is prompt-only and must not receive private or sensitive material"
        )

    if not errors and session_meta is not None:
        print(
            "OK: completed runtime receipt "
            f"thread={session_meta.get('id')}, parent={parent}, depth={depth}, "
            f"turn={turn_id}, role={session_meta.get('agent_role')}, model={model}, "
            f"reasoning_effort={effort}, sandbox={sandbox}"
        )
        print(f"OK: verified rollout {path}")
    return errors, warnings


def load_single_session_meta(path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    document = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid JSONL at {path}:{line_number}: {exc}"
                    ) from exc
                payload = document.get("payload")
                if document.get("type") == "session_meta" and isinstance(payload, dict):
                    records.append(payload)
    except OSError as exc:
        raise ValueError(f"cannot read rollout {path}: {exc}") from exc
    if len(records) != 1:
        raise ValueError(
            f"{path} contains {len(records)} session_meta records; expected 1"
        )
    return records[0]


def _parse_spawn_arguments(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def validate_spawn_provenance(
    parent_path: Path,
    child_path: Path,
    role_name: str,
    expected_call_id: str | None = None,
    allow_generic_worker: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        parent_meta = load_single_session_meta(parent_path)
        child_meta = load_single_session_meta(child_path)
    except ValueError as exc:
        return [str(exc)], warnings

    depth, spawned_parent, spawned_role, agent_path = _spawn_metadata(child_meta)
    child_parent = child_meta.get("parent_thread_id") or spawned_parent
    if parent_meta.get("id") != child_parent:
        errors.append(
            "parent rollout id does not match child parent_thread_id: "
            f"{parent_meta.get('id')!r} != {child_parent!r}"
        )
    if spawned_role != role_name or child_meta.get("agent_role") != role_name:
        errors.append(
            f"child provenance role does not match selected role {role_name!r}"
        )
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
        errors.append(f"child provenance depth is invalid: {depth!r}")
    if not isinstance(agent_path, str) or not agent_path.strip("/"):
        errors.append(f"child provenance agent_path is invalid: {agent_path!r}")
        task_name = None
    else:
        task_name = agent_path.rstrip("/").rsplit("/", 1)[-1]

    calls: list[tuple[str | None, dict[str, Any]]] = []
    try:
        with parent_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    document = json.loads(line)
                except json.JSONDecodeError as exc:
                    return [f"invalid JSONL at {parent_path}:{line_number}: {exc}"], warnings
                payload = document.get("payload")
                if not isinstance(payload, dict):
                    continue
                name = payload.get("name")
                if (
                    document.get("type") == "response_item"
                    and payload.get("type") == "function_call"
                    and isinstance(name, str)
                    and (
                        name == "spawn_agent"
                        or name.endswith(".spawn_agent")
                        or name.endswith("__spawn_agent")
                    )
                ):
                    arguments = _parse_spawn_arguments(payload.get("arguments"))
                    if arguments is not None and arguments.get("task_name") == task_name:
                        call_id = payload.get("call_id")
                        calls.append((call_id if isinstance(call_id, str) else None, arguments))
    except OSError as exc:
        return [f"cannot read parent rollout {parent_path}: {exc}"], warnings

    if len(calls) != 1:
        errors.append(
            f"expected one parent spawn request for task_name={task_name!r}, "
            f"found {len(calls)}"
        )
        return errors, warnings

    call_id, arguments = calls[0]
    if expected_call_id is not None and call_id != expected_call_id:
        errors.append(
            f"spawn request call_id does not match ledger: {call_id!r} != "
            f"{expected_call_id!r}"
        )
    message = arguments.get("message")
    if not isinstance(message, str) or not message:
        errors.append("matching spawn request has no non-empty message")
    explicit_role = arguments.get("agent_type")
    if explicit_role is not None and explicit_role != role_name:
        errors.append(
            f"spawn request agent_type must be {role_name!r}, got {explicit_role!r}"
        )
    elif explicit_role is None and role_name != "default":
        errors.append(
            f"custom role {role_name!r} was not explicitly selected in spawn request"
        )
    elif explicit_role is None:
        errors.append(
            "default role was not explicitly selected with agent_type='default'; "
            "this production contract does not accept implicit role resolution"
        )

    if "fork_turns" in arguments:
        if arguments.get("fork_turns") != "none":
            errors.append(
                f"spawn request fork_turns must be 'none', got {arguments.get('fork_turns')!r}"
            )
    elif "fork_context" in arguments:
        if arguments.get("fork_context") is not False:
            errors.append(
                "spawn request fork_context must be false, got "
                f"{arguments.get('fork_context')!r}"
            )
        if explicit_role is None:
            errors.append("legacy fork_context route requires explicit agent_type")
    else:
        errors.append("spawn request contains no supported non-history route")

    explicit_model = arguments.get("model")
    explicit_effort = arguments.get("reasoning_effort")
    if role_name == "worker" and not allow_generic_worker:
        errors.append("generic worker provenance requires --allow-generic-worker")
    if role_name == "worker" and allow_generic_worker:
        if explicit_model != EXPECTED_MODEL:
            errors.append(
                "generic worker spawn request must explicitly set model="
                f"{EXPECTED_MODEL!r}"
            )
        if explicit_effort != EXPECTED_REASONING_EFFORT:
            errors.append(
                "generic worker spawn request must explicitly set reasoning_effort="
                f"{EXPECTED_REASONING_EFFORT!r}"
            )
    if explicit_model is not None and explicit_model != EXPECTED_MODEL:
        errors.append(
            f"spawn request model conflicts with Luna policy: {explicit_model!r}"
        )
    if explicit_effort is not None and explicit_effort != EXPECTED_REASONING_EFFORT:
        errors.append(
            "spawn request reasoning_effort conflicts with medium policy: "
            f"{explicit_effort!r}"
        )

    if not errors:
        print(
            "OK: spawn provenance "
            f"parent={parent_meta.get('id')}, call_id={call_id}, "
            f"task_name={task_name}, child={child_meta.get('id')}"
        )
    return errors, warnings


def validate_ledger_receipts(
    path: Path,
    codex_home: Path,
) -> tuple[list[str], list[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            ledger = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read research ledger JSON {path}: {exc}"], []
    assignments = ledger.get("assignments") if isinstance(ledger, dict) else None
    if not isinstance(assignments, list) and isinstance(ledger, dict):
        assignments = ledger.get("attempts")
    if not isinstance(assignments, list):
        return ["ledger.assignments must be an array before receipt verification"], []

    errors: list[str] = []
    warnings: list[str] = []
    by_attempt = {
        row.get("attempt_id"): row
        for row in assignments
        if isinstance(row, dict) and isinstance(row.get("attempt_id"), str)
    }
    for index, row in enumerate(assignments):
        if not isinstance(row, dict) or row.get("acceptance_status") != "accepted":
            continue
        thread_id = row.get("thread_uuid")
        turn_id = row.get("runtime_turn")
        role = row.get("agent_role")
        parent_id = row.get("parent_thread_uuid")
        parent_call_id = row.get("parent_call_id")
        delegated = row.get("delegated_by")
        if (
            not isinstance(thread_id, str)
            or not isinstance(turn_id, str)
            or not isinstance(role, str)
            or not isinstance(parent_id, str)
            or not isinstance(parent_call_id, str)
            or row.get("spawn_kind") != "spawn_agent"
        ):
            errors.append(
                f"assignments[{index}] lacks exact child and parent spawn provenance"
            )
            continue
        if not isinstance(delegated, dict):
            if ledger.get("version") == 2:
                errors.append(f"assignments[{index}] lacks delegated_by edge provenance")
                continue
            delegated = {
                "parent_thread_uuid": parent_id,
                "parent_call_id": parent_call_id,
            }
        if (
            delegated.get("parent_thread_uuid") != parent_id
            or delegated.get("parent_call_id") != parent_call_id
        ):
            errors.append(
                f"assignments[{index}] accepted edge does not match delegated_by"
            )
        parent_attempt_id = row.get("parent_attempt_id")
        if parent_attempt_id is not None:
            parent_row = by_attempt.get(parent_attempt_id)
            if not isinstance(parent_row, dict):
                errors.append(
                    f"assignments[{index}] parent_attempt_id is missing from ledger"
                )
            elif parent_row.get("thread_uuid") != parent_id:
                errors.append(
                    f"assignments[{index}] parent thread does not match parent attempt"
                )
        try:
            rollout = find_runtime_rollout(codex_home, thread_id)
            parent_rollout = find_runtime_rollout(codex_home, parent_id)
        except ValueError as exc:
            errors.append(f"assignments[{index}]: {exc}")
            continue
        # Inspect the actual JSONL, not a claimed ledger flag. Leaves may not
        # spawn. Coordinators may spawn exactly the child edges leased in this
        # ledger and no others.
        actual_spawn_call_ids: list[str] = []
        try:
            with rollout.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    doc = json.loads(line)
                    payload = doc.get("payload") if isinstance(doc, dict) else None
                    if isinstance(payload, dict) and doc.get("type") == "response_item" and payload.get("type") == "function_call":
                        name = payload.get("name")
                        if isinstance(name, str) and (name == "spawn_agent" or name.endswith(".spawn_agent") or name.endswith("__spawn_agent")):
                            call_id = payload.get("call_id")
                            if not isinstance(call_id, str) or not call_id.strip():
                                errors.append(
                                    f"assignments[{index}]: spawn_agent call at line {line_number} has no call_id"
                                )
                            else:
                                actual_spawn_call_ids.append(call_id)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"assignments[{index}]: cannot scan child rollout: {exc}")
        coordinator_roles = {
            "coordinator",
            "research_coordinator",
            "luna_project_coordinator",
        }
        is_coordinator = (
            row.get("role") in coordinator_roles
            or row.get("kind") == "coordinator"
            or row.get("agent_role") in coordinator_roles
        )
        if is_coordinator:
            attempt_id = row.get("attempt_id")
            child_rows = [
                child
                for child in assignments
                if isinstance(child, dict)
                and child.get("parent_attempt_id") == attempt_id
            ]
            expected_spawn_call_ids = {
                child.get("delegated_by", {}).get("parent_call_id")
                for child in child_rows
                if isinstance(child.get("delegated_by"), dict)
            }
            if None in expected_spawn_call_ids:
                errors.append(
                    f"assignments[{index}]: coordinator child lacks delegated call ID"
                )
                expected_spawn_call_ids.discard(None)
            if len(actual_spawn_call_ids) != len(set(actual_spawn_call_ids)):
                errors.append(
                    f"assignments[{index}]: coordinator repeated a spawn call ID"
                )
            if set(actual_spawn_call_ids) != expected_spawn_call_ids:
                errors.append(
                    f"assignments[{index}]: coordinator actual spawn calls do not "
                    "match the leased child edges"
                )
            descendant_budget = row.get("descendant_budget")
            if isinstance(descendant_budget, int) and len(actual_spawn_call_ids) > descendant_budget:
                errors.append(
                    f"assignments[{index}]: coordinator exceeded descendant_budget"
                )
        elif actual_spawn_call_ids:
            errors.append(
                f"assignments[{index}]: leaf rollout contains actual spawn_agent call"
            )
        receipt_errors, receipt_warnings = validate_runtime_rollout(
            rollout,
            role,
            row.get("access_mode") == "sandbox_read_only",
            turn_id,
        )
        errors.extend(f"assignments[{index}]: {value}" for value in receipt_errors)
        warnings.extend(f"assignments[{index}]: {value}" for value in receipt_warnings)
        provenance_errors, provenance_warnings = validate_spawn_provenance(
            parent_rollout,
            rollout,
            role,
            parent_call_id,
        )
        errors.extend(
            f"assignments[{index}]: {value}" for value in provenance_errors
        )
        warnings.extend(
            f"assignments[{index}]: {value}" for value in provenance_warnings
        )
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    codex_home = args.codex_home.expanduser().resolve()
    workspace = args.workspace.expanduser().resolve()
    config_paths = [codex_home / "config.toml", *args.config]

    config: dict[str, Any] = {}
    try:
        for position, path in enumerate(config_paths):
            resolved = path.expanduser().resolve()
            if resolved.is_file():
                config = merge_config(config, load_toml(resolved))
            elif position > 0:
                raise ValueError(f"config overlay was not found: {resolved}")
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    errors, warnings = validate_static_base(config)
    definitions, role_warnings = load_role_definitions(
        workspace, codex_home, args.agent_role
    )
    warnings.extend(role_warnings)
    role_errors, more_role_warnings = validate_role_policy(
        config, definitions, args.agent_role, args.allow_generic_worker
    )
    errors.extend(role_errors)
    warnings.extend(more_role_warnings)
    override_errors, override_warnings = validate_workspace_config_overrides(
        workspace, codex_home, args.agent_role
    )
    errors.extend(override_errors)
    warnings.extend(override_warnings)

    if args.spawn_schema_json:
        schema_errors, schema_warnings = validate_spawn_schema(
            args.spawn_schema_json.expanduser().resolve(), args.agent_role
        )
        errors.extend(schema_errors)
        warnings.extend(schema_warnings)
    if args.ledger_json:
        configured_cap = None
        configured_agents = config.get("agents")
        if isinstance(configured_agents, dict):
            raw_cap = configured_agents.get("max_concurrent_threads_per_session")
            if isinstance(raw_cap, int) and not isinstance(raw_cap, bool):
                configured_cap = raw_cap
        ledger_errors, ledger_warnings = validate_assignment_ledger(
            args.ledger_json.expanduser().resolve(), configured_cap=configured_cap
        )
        errors.extend(ledger_errors)
        warnings.extend(ledger_warnings)
        if args.verify_ledger_receipts and not ledger_errors:
            receipt_errors, receipt_warnings = validate_ledger_receipts(
                args.ledger_json.expanduser().resolve(), codex_home
            )
            errors.extend(receipt_errors)
            warnings.extend(receipt_warnings)
    elif args.verify_ledger_receipts:
        errors.append("--verify-ledger-receipts requires --ledger-json")

    runtime_path: Path | None = None
    if args.runtime_rollout:
        runtime_path = args.runtime_rollout.expanduser().resolve()
    elif args.runtime_thread:
        try:
            runtime_path = find_runtime_rollout(codex_home, args.runtime_thread)
        except ValueError as exc:
            errors.append(str(exc))
    if runtime_path is not None:
        runtime_errors, runtime_warnings = validate_runtime_rollout(
            runtime_path,
            args.agent_role,
            args.require_read_only,
            args.runtime_turn,
            args.allow_generic_worker,
        )
        errors.extend(runtime_errors)
        warnings.extend(runtime_warnings)
    elif args.runtime_turn:
        errors.append("--runtime-turn requires --runtime-thread or --runtime-rollout")
    if args.require_read_only and runtime_path is None:
        errors.append("--require-read-only requires a runtime rollout or thread")

    provenance_requested = args.require_spawn_provenance or args.parent_rollout is not None
    if provenance_requested and runtime_path is None:
        errors.append(
            "spawn provenance requires --runtime-thread or --runtime-rollout"
        )
    elif provenance_requested and runtime_path is not None:
        parent_path: Path | None = None
        if args.parent_rollout is not None:
            parent_path = args.parent_rollout.expanduser().resolve()
        else:
            try:
                child_meta = load_single_session_meta(runtime_path)
                _, spawned_parent, _, _ = _spawn_metadata(child_meta)
                parent_id = child_meta.get("parent_thread_id") or spawned_parent
                if not isinstance(parent_id, str):
                    raise ValueError(
                        f"child rollout has no parent thread UUID: {parent_id!r}"
                    )
                parent_path = find_runtime_rollout(codex_home, parent_id)
            except ValueError as exc:
                errors.append(str(exc))
        if parent_path is not None:
            provenance_errors, provenance_warnings = validate_spawn_provenance(
                parent_path,
                runtime_path,
                args.agent_role,
                allow_generic_worker=args.allow_generic_worker,
            )
            errors.extend(provenance_errors)
            warnings.extend(provenance_warnings)

    for warning in sorted(set(warnings)):
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        "READY: skill-local Luna/medium routing policy passed the available checks."
    )
    print(
        "REQUIRED: select one complete live non-history route; do not combine "
        "fields across schema variants."
    )
    print(
        "NOTE: task names, nicknames, prompts, and static configuration are not "
        "completed runtime evidence."
    )
    if runtime_path is None:
        print(
            "NEXT: verify a completed probe with --runtime-thread "
            "<child-thread-uuid>; add --require-read-only only for non-external "
            "lanes requiring a filesystem read-only receipt; keep connector/provider "
            "work root-only."
        )
    else:
        print("VERIFIED: this completed child executed with Luna/medium metadata.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
