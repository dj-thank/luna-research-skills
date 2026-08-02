#!/usr/bin/env python3
"""Fail-closed static and runtime checks for Luna-pinned project workstreams."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

EXPECTED_MODEL = "gpt-5.6-luna"
EXPECTED_REASONING_EFFORT = "medium"
EXPECTED_MAX_THREADS = 40

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on old Python only
    print("ERROR: Python 3.11+ is required (tomllib is unavailable).")
    raise SystemExit(2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Luna-pinned ordinary-agent project fan-out."
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home containing config.toml.",
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
        help="Workspace whose ancestor .codex layers are checked for role overrides.",
    )
    parser.add_argument(
        "--spawn-schema-json",
        type=Path,
        help="Optional captured request or tool-schema JSON containing spawn_agent.",
    )
    runtime = parser.add_mutually_exclusive_group()
    runtime.add_argument(
        "--runtime-rollout",
        type=Path,
        help="Child-agent JSONL rollout whose effective model must be Luna.",
    )
    runtime.add_argument(
        "--runtime-thread",
        help="Child thread UUID; locate its rollout below CODEX_HOME/sessions.",
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


def validate_static(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    agents = config.get("agents")
    if not isinstance(agents, dict):
        errors.append("[agents] must be a TOML table")
        agents = {}

    expected = {
        "enabled": True,
        "max_concurrent_threads_per_session": EXPECTED_MAX_THREADS,
        "default_subagent_model": EXPECTED_MODEL,
        "default_subagent_reasoning_effort": EXPECTED_REASONING_EFFORT,
    }
    for key, value in expected.items():
        current = agents.get(key)
        if current != value or (type(value) is int and isinstance(current, bool)):
            errors.append(f"agents.{key} must be {value}, got {current!r}")
        else:
            print(f"OK: configured agents.{key} = {value}")
    return errors, warnings


def validate_workspace_overrides(
    workspace: Path, codex_home: Path
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    workspace = workspace.expanduser().resolve()
    codex_home = codex_home.expanduser().resolve()
    checked: set[Path] = set()

    agent_dirs = [codex_home / "agents"]
    agent_dirs.extend(directory / ".codex" / "agents" for directory in (workspace, *workspace.parents))
    for agents_dir in agent_dirs:
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
            if role.get("name") != "default":
                continue
            checked.add(role_path.resolve())
            model = role.get("model")
            effort = role.get("model_reasoning_effort")
            if model is not None and model != EXPECTED_MODEL:
                errors.append(f"{role_path}: custom default model overrides Luna with {model!r}")
            if effort is not None and effort != EXPECTED_REASONING_EFFORT:
                errors.append(
                    f"{role_path}: custom default reasoning effort overrides medium with {effort!r}"
                )

    for directory in (workspace, *workspace.parents):
        config_dir = directory / ".codex"
        try:
            if config_dir.resolve() == codex_home:
                continue
        except OSError:
            pass

        config_path = config_dir / "config.toml"
        if not config_path.is_file():
            continue
        try:
            layer = load_toml(config_path)
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        checked.add(config_path.resolve())
        agents = layer.get("agents")
        if not isinstance(agents, dict):
            continue
        expected = {
            "enabled": True,
            "max_concurrent_threads_per_session": EXPECTED_MAX_THREADS,
            "default_subagent_model": EXPECTED_MODEL,
            "default_subagent_reasoning_effort": EXPECTED_REASONING_EFFORT,
        }
        for key, value in expected.items():
            if key in agents and agents[key] != value:
                errors.append(
                    f"{config_path}: agents.{key} overrides the Luna default with "
                    f"{agents[key]!r}"
                )

    if checked and not errors:
        print(f"OK: {len(checked)} workspace config layer(s) do not shadow Luna defaults")
    elif not checked:
        print("OK: no workspace config layer shadows the user Luna defaults")
    return errors, warnings


def spawn_agent_schemas(value: object) -> list[dict[str, Any]]:
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
            found.extend(spawn_agent_schemas(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(spawn_agent_schemas(child))
    return found


def spawn_agent_properties(schema: dict[str, Any]) -> dict[str, Any]:
    for key in ("parameters", "inputSchema", "input_schema"):
        candidate = schema.get(key)
        if isinstance(candidate, dict) and isinstance(
            candidate.get("properties"), dict
        ):
            return candidate["properties"]
    return {}


def validate_spawn_schema(path: Path) -> tuple[list[str], list[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read spawn schema JSON {path}: {exc}"], []

    schemas = spawn_agent_schemas(document)
    if not schemas:
        return [f"{path} contains no spawn_agent declaration"], []

    usable: list[set[str]] = []
    for schema in schemas:
        properties = spawn_agent_properties(schema)
        if isinstance(properties.get("message"), dict):
            usable.append(set(properties))
    if not usable:
        return ["spawn_agent schema does not expose the required message field"], []

    fields = sorted(set().union(*usable))
    print(f"OK: ordinary spawn_agent is callable with fields: {', '.join(fields)}")

    routing_modes: list[str] = []
    for fields_for_schema in usable:
        if "fork_turns" in fields_for_schema:
            routing_modes.append("fork_turns")
        if {"agent_type", "fork_context"}.issubset(fields_for_schema):
            routing_modes.append("current agent_type/fork_context")
    if not routing_modes:
        return [
            "spawn_agent must expose either message/fork_turns or "
            "message/agent_type/fork_context routing controls"
        ], []
    print("OK: supported non-history routing: " + ", ".join(sorted(set(routing_modes))))
    return [], []


def rollout_has_thread(path: Path, thread_id: str) -> bool:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                document = json.loads(line)
                if document.get("type") == "session_meta":
                    payload = document.get("payload")
                    return isinstance(payload, dict) and payload.get("id") == thread_id
    except (OSError, json.JSONDecodeError):
        return False
    return False


def find_runtime_rollout(codex_home: Path, thread_id: str) -> Path:
    try:
        normalized = str(uuid.UUID(thread_id))
    except ValueError as exc:
        raise ValueError(f"runtime thread must be a UUID, got {thread_id!r}") from exc
    sessions = codex_home / "sessions"
    if not sessions.is_dir():
        raise ValueError(f"sessions directory is missing: {sessions}")
    matches = [
        path
        for path in sessions.rglob(f"*{normalized}.jsonl")
        if rollout_has_thread(path, normalized)
    ]
    if not matches:
        raise ValueError(f"no child rollout found for thread {normalized}")
    return max(matches, key=lambda path: path.stat().st_mtime_ns)


def validate_runtime_rollout(path: Path) -> tuple[list[str], list[str]]:
    latest_context: dict[str, Any] | None = None
    session_meta: dict[str, Any] | None = None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    document = json.loads(line)
                except json.JSONDecodeError as exc:
                    return [f"invalid JSONL at {path}:{line_number}: {exc}"], []
                payload = document.get("payload")
                if document.get("type") == "session_meta" and isinstance(payload, dict):
                    session_meta = payload
                if document.get("type") == "turn_context" and isinstance(payload, dict):
                    latest_context = payload
    except OSError as exc:
        return [f"cannot read runtime rollout {path}: {exc}"], []

    errors: list[str] = []
    if session_meta is None:
        errors.append(f"{path} contains no session_meta")
    elif session_meta.get("thread_source") != "subagent":
        errors.append("runtime rollout is not identified as a subagent thread")
    if latest_context is None:
        errors.append(f"{path} contains no turn_context runtime metadata")
        return errors, []

    model = latest_context.get("model")
    effort = latest_context.get("effort")
    if model != EXPECTED_MODEL:
        errors.append(f"runtime model must be {EXPECTED_MODEL!r}, got {model!r}")
    if effort != EXPECTED_REASONING_EFFORT:
        errors.append(
            "runtime reasoning effort must be "
            f"{EXPECTED_REASONING_EFFORT!r}, got {effort!r}"
        )
    if not errors:
        print(f"OK: child runtime reports model={model}, reasoning_effort={effort}")
        print(f"OK: verified rollout {path}")
    return errors, []


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    codex_home = args.codex_home.expanduser().resolve()
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

    errors, warnings = validate_static(config)
    override_errors, override_warnings = validate_workspace_overrides(
        args.workspace, codex_home
    )
    errors.extend(override_errors)
    warnings.extend(override_warnings)
    if args.spawn_schema_json:
        schema_errors, schema_warnings = validate_spawn_schema(
            args.spawn_schema_json.expanduser().resolve()
        )
        errors.extend(schema_errors)
        warnings.extend(schema_warnings)

    runtime_path: Path | None = None
    if args.runtime_rollout:
        runtime_path = args.runtime_rollout.expanduser().resolve()
    elif args.runtime_thread:
        try:
            runtime_path = find_runtime_rollout(codex_home, args.runtime_thread)
        except ValueError as exc:
            errors.append(str(exc))
    if runtime_path is not None:
        runtime_errors, runtime_warnings = validate_runtime_rollout(runtime_path)
        errors.extend(runtime_errors)
        warnings.extend(runtime_warnings)

    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("READY: Codex-native Luna subagent defaults passed preflight.")
    print(
        'REQUIRED: use fork_turns="none" when available; otherwise use '
        'agent_type="default", fork_context=false before accepting a child.'
    )
    print("NOTE: task names and nicknames are logistical labels, not model evidence.")
    if runtime_path is None:
        print("NEXT: verify a completed probe with --runtime-thread <child-thread-uuid>.")
    else:
        print("VERIFIED: this child executed with GPT-5.6 Luna metadata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
