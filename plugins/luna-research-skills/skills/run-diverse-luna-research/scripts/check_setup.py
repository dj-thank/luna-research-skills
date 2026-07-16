#!/usr/bin/env python3
"""Fail-closed static and runtime checks for Luna-pinned research scouts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

EXPECTED_AGENT_NAME = "default"
EXPECTED_MODEL = "gpt-5.6-luna"
EXPECTED_REASONING_EFFORT = "medium"
EXPECTED_MAX_THREADS = 40
EXPECTED_MAX_DEPTH = 2

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on old Python only
    print("ERROR: Python 3.11+ is required (tomllib is unavailable).")
    raise SystemExit(2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Luna-pinned ordinary-agent research fan-out."
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home containing config.toml and agents/default.toml.",
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

    features = config.get("features")
    if not isinstance(features, dict):
        errors.append("[features] must be a TOML table")
    elif features.get("multi_agent") is not True:
        errors.append("features.multi_agent must be true")
    else:
        print("OK: stable multi_agent is enabled")

    agents = config.get("agents")
    if not isinstance(agents, dict):
        errors.append("[agents] must be a TOML table")
        agents = {}

    expected = {
        "max_threads": EXPECTED_MAX_THREADS,
        "max_depth": EXPECTED_MAX_DEPTH,
    }
    for key, value in expected.items():
        current = agents.get(key)
        if isinstance(current, bool) or current != value:
            errors.append(f"agents.{key} must be {value}, got {current!r}")
        else:
            print(f"OK: configured agents.{key} = {value}")
    return errors, warnings


def validate_role_file(path: Path, label: str) -> tuple[list[str], list[str]]:
    if not path.is_file():
        return [f"{label} is missing: {path}"], []
    try:
        role = load_toml(path)
    except ValueError as exc:
        return [str(exc)], []

    errors: list[str] = []
    expected = {
        "name": EXPECTED_AGENT_NAME,
        "model": EXPECTED_MODEL,
        "model_reasoning_effort": EXPECTED_REASONING_EFFORT,
    }
    for key, value in expected.items():
        if role.get(key) != value:
            errors.append(f"{path}: {key} must be {value!r}, got {role.get(key)!r}")
    if not isinstance(role.get("developer_instructions"), str):
        errors.append(f"{path}: developer_instructions must be a string")
    if not errors:
        print(
            "OK: custom default agent pins "
            f"model={EXPECTED_MODEL}, reasoning_effort={EXPECTED_REASONING_EFFORT}"
        )
    return errors, []


def validate_default_agent(codex_home: Path) -> tuple[list[str], list[str]]:
    return validate_role_file(
        codex_home / "agents" / "default.toml", "Luna default-agent file"
    )


def validate_workspace_overrides(
    workspace: Path, codex_home: Path
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    workspace = workspace.expanduser().resolve()
    codex_home = codex_home.expanduser().resolve()
    checked: set[Path] = set()

    for directory in (workspace, *workspace.parents):
        config_dir = directory / ".codex"
        try:
            if config_dir.resolve() == codex_home:
                continue
        except OSError:
            pass

        agents_dir = config_dir / "agents"
        if agents_dir.is_dir():
            try:
                role_paths = sorted(agents_dir.rglob("*.toml"))
            except OSError as exc:
                warnings.append(f"cannot scan {agents_dir}: {exc}")
                role_paths = []
            for path in role_paths:
                try:
                    role = load_toml(path)
                except ValueError as exc:
                    warnings.append(str(exc))
                    continue
                if role.get("name") == EXPECTED_AGENT_NAME:
                    checked.add(path.resolve())
                    role_errors, role_warnings = validate_role_file(
                        path, "workspace default-agent override"
                    )
                    errors.extend(role_errors)
                    warnings.extend(role_warnings)

        config_path = config_dir / "config.toml"
        if not config_path.is_file():
            continue
        try:
            layer = load_toml(config_path)
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        agents = layer.get("agents")
        default = agents.get("default") if isinstance(agents, dict) else None
        config_file = default.get("config_file") if isinstance(default, dict) else None
        if isinstance(config_file, str):
            role_path = Path(config_file)
            if not role_path.is_absolute():
                role_path = config_dir / role_path
            role_path = role_path.resolve()
            if role_path not in checked:
                checked.add(role_path)
                role_errors, role_warnings = validate_role_file(
                    role_path, "workspace agents.default.config_file"
                )
                errors.extend(role_errors)
                warnings.extend(role_warnings)

    if checked and not errors:
        print(f"OK: {len(checked)} workspace default-role override(s) also pin Luna")
    elif not checked:
        print("OK: no workspace default-role override shadows the user Luna role")
    return errors, warnings


def spawn_agent_schemas(value: object) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        name = value.get("name")
        if (
            isinstance(name, str)
            and name.rsplit(".", 1)[-1] == "spawn_agent"
            and isinstance(value.get("parameters"), dict)
        ):
            found.append(value)
        for child in value.values():
            found.extend(spawn_agent_schemas(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(spawn_agent_schemas(child))
    return found


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
        properties = schema.get("parameters", {}).get("properties", {})
        if isinstance(properties, dict) and isinstance(properties.get("message"), dict):
            usable.append(set(properties))
    if not usable:
        return ["spawn_agent schema does not expose the required message field"], []

    fields = sorted(set().union(*usable))
    print(f"OK: ordinary spawn_agent is callable with fields: {', '.join(fields)}")
    if not any("fork_turns" in fields_for_schema for fields_for_schema in usable):
        return [
            "spawn_agent does not expose fork_turns; the Luna default role cannot be "
            "selected deterministically"
        ], []
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
    role_errors, role_warnings = validate_default_agent(codex_home)
    errors.extend(role_errors)
    warnings.extend(role_warnings)
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

    print("READY: static Luna ordinary-agent routing passed preflight.")
    print('REQUIRED: every new spawn must pass fork_turns="none".')
    print("NOTE: task_name and nicknames are logistical labels, not model evidence.")
    if runtime_path is None:
        print("NEXT: verify a completed probe with --runtime-thread <child-thread-uuid>.")
    else:
        print("VERIFIED: this child executed with GPT-5.6 Luna metadata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
