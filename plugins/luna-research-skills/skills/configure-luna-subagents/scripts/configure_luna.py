#!/usr/bin/env python3
"""Plan, install, inspect, and restore the Luna default-subagent configuration."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on old Python only
    print("ERROR: Python 3.11+ is required (tomllib is unavailable).")
    raise SystemExit(2)


EXPECTED_MODEL = "gpt-5.6-luna"
EXPECTED_EFFORT = "medium"
EXPECTED_SETTINGS = (
    ("features", "multi_agent", True),
    ("agents", "max_threads", 40),
    ("agents", "max_depth", 2),
)
STATE_NAME = ".luna-research-skills-state.json"
HEADER_RE = re.compile(r"^\s*\[([^\[\]]+)]\s*(?:#.*)?$")
KEY_RE_TEMPLATE = r"^(\s*){key}\s*=.*$"


class ConfigError(ValueError):
    """Raised when a config cannot be changed without risking unrelated data."""


@dataclass(frozen=True)
class TextFile:
    text: str
    newline: str
    bom: bool

    def encode(self) -> bytes:
        encoding = "utf-8-sig" if self.bom else "utf-8"
        return self.text.encode(encoding)


@dataclass(frozen=True)
class Plan:
    config_before: bytes | None
    config_after: bytes
    role_before: bytes | None
    role_after: bytes
    changes: tuple[str, ...]
    conflicts: tuple[str, ...]
    role_matches: bool


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Safely configure ordinary non-full-history Codex subagents for "
            "GPT-5.6 Luna."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=("status", "plan", "install", "uninstall"),
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home to inspect or change (default: CODEX_HOME or ~/.codex).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Required acknowledgement for install and uninstall writes.",
    )
    parser.add_argument(
        "--replace-default",
        action="store_true",
        help="Back up and replace a conflicting agents/default.toml.",
    )
    parser.add_argument(
        "--replace-settings",
        action="store_true",
        help="Back up and replace conflicting multi-agent limits in config.toml.",
    )
    return parser.parse_args(argv)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def decode_toml(data: bytes | None) -> TextFile:
    if data is None:
        return TextFile("", os.linesep, False)
    bom = data.startswith(codecs.BOM_UTF8)
    try:
        text = data.decode("utf-8-sig" if bom else "utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"config.toml must be UTF-8: {exc}") from exc
    newline = "\r\n" if text.count("\r\n") > text.count("\n") / 2 else "\n"
    return TextFile(text, newline, bom)


def parse_toml(text: str, label: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{label} is not valid TOML: {exc}") from exc
    if not isinstance(value, dict):  # pragma: no cover - tomllib always returns dict
        raise ConfigError(f"{label} must contain a TOML document")
    return value


def structural_headers(lines: list[str]) -> list[tuple[int, str]]:
    """Return TOML table headers while ignoring lines inside multiline strings."""
    headers: list[tuple[int, str]] = []
    multiline: str | None = None
    for index, line in enumerate(lines):
        if multiline is not None:
            if line.count(multiline) % 2 == 1:
                multiline = None
            continue

        code = line.split("#", 1)[0]
        triple_double = code.count('"""')
        triple_single = code.count("'''")
        if triple_double % 2 == 1:
            multiline = '"""'
            continue
        if triple_single % 2 == 1:
            multiline = "'''"
            continue

        match = HEADER_RE.match(line)
        if match:
            headers.append((index, match.group(1).strip()))
    return headers


def nested_value(document: dict[str, Any], table: str, key: str) -> Any:
    section = document.get(table)
    return section.get(key) if isinstance(section, dict) else None


def render_toml_value(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise TypeError(f"unsupported managed TOML value: {value!r}")


def patch_setting(text_file: TextFile, table: str, key: str, value: object) -> TextFile:
    text = text_file.text
    document = parse_toml(text, "config.toml")
    lines = text.splitlines()
    headers = structural_headers(lines)
    matching = [(index, name) for index, name in headers if name == table]

    if len(matching) > 1:
        raise ConfigError(f"config.toml repeats [{table}]; repair it before setup")
    if not matching:
        if table in document:
            raise ConfigError(
                f"config.toml defines {table!r} with a layout this installer cannot "
                "edit safely; use an explicit [{table}] table"
            )
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend((f"[{table}]", f"{key} = {render_toml_value(value)}"))
    else:
        start = matching[0][0]
        later_headers = [index for index, _ in headers if index > start]
        end = min(later_headers) if later_headers else len(lines)
        key_re = re.compile(KEY_RE_TEMPLATE.format(key=re.escape(key)))
        key_lines = [index for index in range(start + 1, end) if key_re.match(lines[index])]
        current = nested_value(document, table, key)
        if len(key_lines) > 1:
            raise ConfigError(f"config.toml repeats {table}.{key}")
        if not key_lines:
            if current is not None:
                raise ConfigError(
                    f"config.toml defines {table}.{key} with a layout this installer "
                    "cannot edit safely"
                )
            lines.insert(end, f"{key} = {render_toml_value(value)}")
        else:
            index = key_lines[0]
            indent = key_re.match(lines[index]).group(1)  # type: ignore[union-attr]
            comment = ""
            if "#" in lines[index]:
                comment = "  #" + lines[index].split("#", 1)[1]
            lines[index] = f"{indent}{key} = {render_toml_value(value)}{comment}"

    patched = text_file.newline.join(lines).rstrip() + text_file.newline
    parsed = parse_toml(patched, "patched config.toml")
    if nested_value(parsed, table, key) != value:
        raise ConfigError(f"failed to set {table}.{key}")
    return TextFile(patched, text_file.newline, text_file.bom)


def expected_role_bytes() -> bytes:
    asset = Path(__file__).resolve().parent.parent / "assets" / "default-agent.toml"
    data = asset.read_bytes()
    role = parse_toml(data.decode("utf-8"), "bundled default-agent.toml")
    if role.get("name") != "default" or role.get("model") != EXPECTED_MODEL:
        raise ConfigError("bundled default-agent.toml failed its integrity check")
    if role.get("model_reasoning_effort") != EXPECTED_EFFORT:
        raise ConfigError("bundled default-agent.toml has an unexpected reasoning effort")
    return data


def role_matches(data: bytes | None) -> bool:
    if data is None:
        return False
    try:
        role = parse_toml(data.decode("utf-8-sig"), "agents/default.toml")
    except (UnicodeDecodeError, ConfigError):
        return False
    return (
        role.get("name") == "default"
        and role.get("model") == EXPECTED_MODEL
        and role.get("model_reasoning_effort") == EXPECTED_EFFORT
        and isinstance(role.get("developer_instructions"), str)
    )


def build_plan(codex_home: Path) -> Plan:
    config_path = codex_home / "config.toml"
    role_path = codex_home / "agents" / "default.toml"
    config_before = read_optional(config_path)
    role_before = read_optional(role_path)

    text_file = decode_toml(config_before)
    document = parse_toml(text_file.text, "config.toml")
    changes: list[str] = []
    conflicts: list[str] = []

    for table, key, expected in EXPECTED_SETTINGS:
        current = nested_value(document, table, key)
        if current != expected:
            shown = "<missing>" if current is None else repr(current)
            changes.append(f"config.toml: {table}.{key}: {shown} -> {expected!r}")
            if current is not None:
                conflicts.append(f"{table}.{key}")
        text_file = patch_setting(text_file, table, key, expected)
        document = parse_toml(text_file.text, "config.toml")

    expected_role = expected_role_bytes()
    matches = role_matches(role_before)
    if not matches:
        changes.append(
            "agents/default.toml: create Luna default role"
            if role_before is None
            else "agents/default.toml: replace existing default role with Luna"
        )
        if role_before is not None:
            conflicts.append("agents/default.toml")

    return Plan(
        config_before=config_before,
        config_after=text_file.encode(),
        role_before=role_before,
        role_after=role_before if matches and role_before is not None else expected_role,
        changes=tuple(changes),
        conflicts=tuple(conflicts),
        role_matches=matches,
    )


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def safe_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_state(path: Path) -> dict[str, Any] | None:
    data = read_optional(path)
    if data is None:
        return None
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"state file is invalid: {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ConfigError(f"state file has an unsupported format: {path}")
    return value


def state_is_current(codex_home: Path, state: dict[str, Any]) -> bool:
    files = state.get("files")
    if not isinstance(files, dict):
        return False
    targets = {
        "config.toml": codex_home / "config.toml",
        "agents/default.toml": codex_home / "agents" / "default.toml",
    }
    for name, target in targets.items():
        record = files.get(name)
        current = read_optional(target)
        if not isinstance(record, dict) or current is None:
            return False
        if record.get("installed_sha256") != sha256(current):
            return False
    return True


def print_plan(plan: Plan) -> None:
    if plan.changes:
        for change in plan.changes:
            print(f"CHANGE: {change}")
    else:
        print("NO CHANGE: Luna configuration already matches the requested state.")
    if plan.conflicts:
        for conflict in plan.conflicts:
            print(f"CONFLICT: {conflict}")
        flags: list[str] = []
        if "agents/default.toml" in plan.conflicts:
            flags.append("--replace-default")
        if any(item != "agents/default.toml" for item in plan.conflicts):
            flags.append("--replace-settings")
        print("REQUIRED FLAGS: " + " ".join(flags))


def command_status(codex_home: Path) -> int:
    state_path = codex_home / STATE_NAME
    try:
        plan = build_plan(codex_home)
        state = load_state(state_path)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2

    print(f"CODEX_HOME: {codex_home}")
    print_plan(plan)
    if state is None:
        print("STATE: no managed installation record")
    elif state_is_current(codex_home, state):
        print("STATE: managed installation is intact")
    else:
        print("STATE: managed files changed after installation")
    if plan.changes:
        print("NOT READY: run plan, review the blast radius, then install explicitly.")
        return 1
    print("READY: static Luna subagent configuration is present.")
    return 0


def command_plan(codex_home: Path) -> int:
    try:
        plan = build_plan(codex_home)
        state = load_state(codex_home / STATE_NAME)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2

    print(f"CODEX_HOME: {codex_home}")
    print_plan(plan)
    if state is not None and not state_is_current(codex_home, state):
        print("BLOCKED: managed files drifted; inspect backups before another install.")
        return 1
    if plan.changes:
        print("PLAN ONLY: no files were changed.")
    else:
        print("READY: no installation changes are needed.")
    return 0


def restore_bytes(path: Path, data: bytes | None) -> None:
    if data is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    else:
        atomic_write(path, data)


def command_install(codex_home: Path, args: argparse.Namespace) -> int:
    if not args.apply:
        print("ERROR: install is write-enabled only with --apply after reviewing plan.")
        return 2
    state_path = codex_home / STATE_NAME
    try:
        state = load_state(state_path)
        if state is not None:
            if state_is_current(codex_home, state):
                plan = build_plan(codex_home)
                if not plan.changes:
                    print("READY: managed Luna configuration is already installed.")
                    return 0
            print("ERROR: a managed state already exists and has drifted; uninstall or restore manually.")
            return 1
        plan = build_plan(codex_home)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2

    print_plan(plan)
    role_conflict = "agents/default.toml" in plan.conflicts
    setting_conflict = any(item != "agents/default.toml" for item in plan.conflicts)
    if role_conflict and not args.replace_default:
        print("BLOCKED: rerun only after approval with --replace-default.")
        return 1
    if setting_conflict and not args.replace_settings:
        print("BLOCKED: rerun only after approval with --replace-settings.")
        return 1
    if not plan.changes:
        print("READY: Luna configuration already matches; no files changed.")
        return 0

    timestamp = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + f"-{uuid.uuid4().hex[:8]}"
    )
    backup_dir = codex_home / "backups" / "luna-research-skills" / timestamp
    config_path = codex_home / "config.toml"
    role_path = codex_home / "agents" / "default.toml"
    originals = {config_path: plan.config_before, role_path: plan.role_before}
    installed = {config_path: plan.config_after, role_path: plan.role_after}
    backup_names = {config_path: "config.toml", role_path: "agents-default.toml"}
    records: dict[str, Any] = {}

    try:
        for target, original in originals.items():
            backup: Path | None = None
            if original is not None:
                backup = backup_dir / backup_names[target]
                atomic_write(backup, original)
            records[safe_relative(target, codex_home)] = {
                "existed": original is not None,
                "original_sha256": sha256(original) if original is not None else None,
                "installed_sha256": sha256(installed[target]),
                "backup": safe_relative(backup, codex_home) if backup else None,
            }
        for target, data in installed.items():
            atomic_write(target, data)
        state_document = {
            "version": 1,
            "installed_at_utc": datetime.now(timezone.utc).isoformat(),
            "model": EXPECTED_MODEL,
            "files": records,
        }
        atomic_write(
            state_path,
            (json.dumps(state_document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    except OSError as exc:
        for target, original in originals.items():
            try:
                restore_bytes(target, original)
            except OSError:
                pass
        print(f"ERROR: installation failed and rollback was attempted: {exc}")
        return 2

    print(f"INSTALLED: model={EXPECTED_MODEL}, max_threads=40, max_depth=2")
    print(f"BACKUP: {backup_dir}")
    print("NEXT: restart Codex or open a new task, then run the Luna runtime preflight.")
    return 0


def resolve_backup(codex_home: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise ConfigError("state file is missing a backup path")
    root = codex_home.resolve()
    candidate = (codex_home / Path(relative)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ConfigError("state file contains a backup path outside CODEX_HOME") from exc
    return candidate


def command_uninstall(codex_home: Path, args: argparse.Namespace) -> int:
    if not args.apply:
        print("ERROR: uninstall is write-enabled only with --apply.")
        return 2
    state_path = codex_home / STATE_NAME
    try:
        state = load_state(state_path)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2
    if state is None:
        print("ERROR: no managed installation record exists; nothing can be restored safely.")
        return 1
    if not state_is_current(codex_home, state):
        print("BLOCKED: a managed file changed after installation; preserve it and restore manually.")
        return 1

    files = state.get("files")
    if not isinstance(files, dict):
        print("ERROR: state file is missing file records.")
        return 2
    targets = {
        "config.toml": codex_home / "config.toml",
        "agents/default.toml": codex_home / "agents" / "default.toml",
    }
    current = {target: read_optional(target) for target in targets.values()}
    restore_map: dict[Path, bytes | None] = {}
    try:
        for name, target in targets.items():
            record = files.get(name)
            if not isinstance(record, dict):
                raise ConfigError(f"state file is missing the {name} record")
            if record.get("existed"):
                backup = resolve_backup(codex_home, record.get("backup"))
                original = backup.read_bytes()
                if sha256(original) != record.get("original_sha256"):
                    raise ConfigError(f"backup integrity check failed: {backup}")
                restore_map[target] = original
            else:
                restore_map[target] = None
        for target, original in restore_map.items():
            restore_bytes(target, original)
        state_path.unlink()
    except (ConfigError, OSError) as exc:
        for target, data in current.items():
            try:
                restore_bytes(target, data)
            except OSError:
                pass
        print(f"ERROR: restore failed and rollback was attempted: {exc}")
        return 2

    print("RESTORED: pre-install config.toml and agents/default.toml state.")
    print("NOTE: timestamped backups were retained for manual recovery.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    codex_home = args.codex_home.expanduser().resolve()
    if args.command == "status":
        return command_status(codex_home)
    if args.command == "plan":
        return command_plan(codex_home)
    if args.command == "install":
        return command_install(codex_home, args)
    return command_uninstall(codex_home, args)


if __name__ == "__main__":
    sys.exit(main())
