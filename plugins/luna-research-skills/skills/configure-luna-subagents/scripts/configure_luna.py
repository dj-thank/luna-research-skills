#!/usr/bin/env python3
"""Plan, install, inspect, migrate, and restore Codex Luna defaults."""

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
except ModuleNotFoundError:  # pragma: no cover
    print("ERROR: Python 3.11+ is required (tomllib is unavailable).")
    raise SystemExit(2)


EXPECTED_MODEL = "gpt-5.6-luna"
EXPECTED_EFFORT = "medium"
EXPECTED_THREADS = 40
EXPECTED_SETTINGS = (
    ("agents", "enabled", True),
    ("agents", "max_concurrent_threads_per_session", EXPECTED_THREADS),
    ("agents", "default_subagent_model", EXPECTED_MODEL),
    ("agents", "default_subagent_reasoning_effort", EXPECTED_EFFORT),
)
STATE_NAME = ".luna-research-skills-state.json"
STATE_VERSION = 2
HEADER_RE = re.compile(r"^\s*\[([^\[\]]+)]\s*(?:#.*)?$")
KEY_RE_TEMPLATE = r"^(\s*){key}\s*=.*$"
ALLOWED_MANAGED_FILES = {"config.toml", "agents/default.toml"}


class ConfigError(ValueError):
    """Raised when a config cannot be changed without risking unrelated data."""


@dataclass(frozen=True)
class TextFile:
    text: str
    newline: str
    bom: bool

    def encode(self) -> bytes:
        return self.text.encode("utf-8-sig" if self.bom else "utf-8")


@dataclass(frozen=True)
class Plan:
    config_before: bytes | None
    config_after: bytes
    changes: tuple[str, ...]
    conflicts: tuple[str, ...]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely configure Codex subagent defaults for GPT-5.6 Luna."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=("status", "plan", "install", "migrate", "uninstall"),
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home to inspect or change (default: CODEX_HOME or ~/.codex).",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Required acknowledgement for writes."
    )
    parser.add_argument(
        "--replace-settings",
        action="store_true",
        help="Allow replacement of conflicting managed [agents] values.",
    )
    parser.add_argument(
        "--replace-default",
        action="store_true",
        help=argparse.SUPPRESS,
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
    return value


def structural_headers(lines: list[str]) -> list[tuple[int, str]]:
    headers: list[tuple[int, str]] = []
    multiline: str | None = None
    for index, line in enumerate(lines):
        if multiline is not None:
            if line.count(multiline) % 2 == 1:
                multiline = None
            continue
        code = line.split("#", 1)[0]
        if code.count('"""') % 2 == 1:
            multiline = '"""'
            continue
        if code.count("'''") % 2 == 1:
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
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"unsupported managed TOML value: {value!r}")


def patch_setting(text_file: TextFile, table: str, key: str, value: object) -> TextFile:
    document = parse_toml(text_file.text, "config.toml")
    lines = text_file.text.splitlines()
    headers = structural_headers(lines)
    matching = [(index, name) for index, name in headers if name == table]
    if len(matching) > 1:
        raise ConfigError(f"config.toml repeats [{table}]; repair it before setup")
    if not matching:
        if table in document:
            raise ConfigError(
                f"config.toml defines {table!r} with a layout this installer cannot edit safely"
            )
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend((f"[{table}]", f"{key} = {render_toml_value(value)}"))
    else:
        start = matching[0][0]
        later = [index for index, _ in headers if index > start]
        end = min(later) if later else len(lines)
        key_re = re.compile(KEY_RE_TEMPLATE.format(key=re.escape(key)))
        key_lines = [index for index in range(start + 1, end) if key_re.match(lines[index])]
        current = nested_value(document, table, key)
        if len(key_lines) > 1:
            raise ConfigError(f"config.toml repeats {table}.{key}")
        if not key_lines:
            if current is not None:
                raise ConfigError(
                    f"config.toml defines {table}.{key} with a layout this installer cannot edit safely"
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


def build_plan_from_bytes(config_before: bytes | None) -> Plan:
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
    return Plan(config_before, text_file.encode(), tuple(changes), tuple(conflicts))


def build_plan(codex_home: Path) -> Plan:
    return build_plan_from_bytes(read_optional(codex_home / "config.toml"))


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
    if not isinstance(value, dict) or value.get("version") not in (1, STATE_VERSION):
        raise ConfigError(f"state file has an unsupported format: {path}")
    return value


def state_targets(codex_home: Path, state: dict[str, Any]) -> dict[str, Path]:
    files = state.get("files")
    if not isinstance(files, dict) or not files:
        raise ConfigError("state file is missing file records")
    targets: dict[str, Path] = {}
    for name in files:
        if name not in ALLOWED_MANAGED_FILES:
            raise ConfigError(f"state file contains unsupported managed path: {name}")
        targets[name] = codex_home / Path(name)
    return targets


def state_is_current(codex_home: Path, state: dict[str, Any]) -> bool:
    try:
        targets = state_targets(codex_home, state)
    except ConfigError:
        return False
    files = state["files"]
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
        print("NO CHANGE: Luna defaults already match the requested state.")
    for conflict in plan.conflicts:
        print(f"CONFLICT: {conflict}")
    if plan.conflicts:
        print("REQUIRED FLAGS: --replace-settings")


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


def originals_from_state(codex_home: Path, state: dict[str, Any]) -> dict[Path, bytes | None]:
    files = state["files"]
    originals: dict[Path, bytes | None] = {}
    for name, target in state_targets(codex_home, state).items():
        record = files.get(name)
        if not isinstance(record, dict):
            raise ConfigError(f"state file is missing the {name} record")
        if record.get("existed"):
            backup = resolve_backup(codex_home, record.get("backup"))
            original = backup.read_bytes()
            if sha256(original) != record.get("original_sha256"):
                raise ConfigError(f"backup integrity check failed: {backup}")
            originals[target] = original
        else:
            originals[target] = None
    return originals


def restore_bytes(path: Path, data: bytes | None) -> None:
    if data is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    else:
        atomic_write(path, data)


def command_status(codex_home: Path) -> int:
    try:
        plan = build_plan(codex_home)
        state = load_state(codex_home / STATE_NAME)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"CODEX_HOME: {codex_home}")
    print_plan(plan)
    if state is None:
        print("STATE: no managed installation record")
    elif state_is_current(codex_home, state):
        print(f"STATE: managed v{state['version']} installation is intact")
    else:
        print("STATE: managed files changed after installation")
    if plan.changes:
        print("NOT READY: review the plan, then install or migrate explicitly.")
        return 1
    print("READY: Codex-native Luna subagent defaults are present.")
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
    if state is not None:
        if not state_is_current(codex_home, state):
            print("BLOCKED: managed files drifted; inspect backups before another write.")
            return 1
        if state.get("version") == 1:
            print("MIGRATION: run migrate --apply after reviewing conflicts.")
    print("PLAN ONLY: no files were changed." if plan.changes else "READY: no changes are needed.")
    return 0


def timestamped_backup(codex_home: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return codex_home / "backups" / "luna-research-skills" / f"{stamp}-{uuid.uuid4().hex[:8]}"


def install_plan(codex_home: Path, plan: Plan) -> None:
    config_path = codex_home / "config.toml"
    state_path = codex_home / STATE_NAME
    backup_dir = timestamped_backup(codex_home)
    backup: Path | None = None
    if plan.config_before is not None:
        backup = backup_dir / "config.toml"
        atomic_write(backup, plan.config_before)
    record = {
        "existed": plan.config_before is not None,
        "original_sha256": sha256(plan.config_before) if plan.config_before is not None else None,
        "installed_sha256": sha256(plan.config_after),
        "backup": safe_relative(backup, codex_home) if backup else None,
    }
    atomic_write(config_path, plan.config_after)
    state = {
        "version": STATE_VERSION,
        "installed_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": EXPECTED_MODEL,
        "files": {"config.toml": record},
    }
    atomic_write(state_path, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
    print(
        f"INSTALLED: model={EXPECTED_MODEL}, reasoning_effort={EXPECTED_EFFORT}, "
        f"max_concurrent_threads_per_session={EXPECTED_THREADS}"
    )
    print(f"BACKUP: {backup_dir}")
    print("NEXT: restart Codex or open a new task, then run the Luna runtime preflight.")


def command_install(codex_home: Path, args: argparse.Namespace) -> int:
    if not args.apply:
        print("ERROR: install requires --apply after reviewing plan.")
        return 2
    state_path = codex_home / STATE_NAME
    try:
        state = load_state(state_path)
        if state is not None:
            if state.get("version") == 1 and state_is_current(codex_home, state):
                print("BLOCKED: legacy managed state detected; use migrate --apply.")
            else:
                print("BLOCKED: managed state already exists; use status or uninstall.")
            return 1
        plan = build_plan(codex_home)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 2
    print_plan(plan)
    if plan.conflicts and not args.replace_settings:
        print("BLOCKED: rerun only after approval with --replace-settings.")
        return 1
    if not plan.changes:
        print("READY: Luna defaults already match; no files changed.")
        return 0
    try:
        install_plan(codex_home, plan)
    except OSError as exc:
        restore_bytes(codex_home / "config.toml", plan.config_before)
        try:
            state_path.unlink()
        except FileNotFoundError:
            pass
        print(f"ERROR: installation failed and rollback was attempted: {exc}")
        return 2
    return 0


def command_migrate(codex_home: Path, args: argparse.Namespace) -> int:
    if not args.apply:
        print("ERROR: migrate requires --apply after reviewing plan.")
        return 2
    state_path = codex_home / STATE_NAME
    try:
        state = load_state(state_path)
        if state is None or state.get("version") != 1:
            print("ERROR: migrate requires an intact managed v1 installation.")
            return 1
        if not state_is_current(codex_home, state):
            print("BLOCKED: managed v1 files drifted; preserve them and restore manually.")
            return 1
        originals = originals_from_state(codex_home, state)
        original_config = originals.get(codex_home / "config.toml")
        plan = build_plan_from_bytes(original_config)
    except (ConfigError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print_plan(plan)
    if plan.conflicts and not args.replace_settings:
        print("BLOCKED: rerun only after approval with --replace-settings.")
        return 1
    current = {path: read_optional(path) for path in originals}
    current_state = read_optional(state_path)
    try:
        for path, original in originals.items():
            restore_bytes(path, original)
        state_path.unlink()
        install_plan(codex_home, plan)
    except OSError as exc:
        for path, data in current.items():
            restore_bytes(path, data)
        if current_state is not None:
            atomic_write(state_path, current_state)
        print(f"ERROR: migration failed and rollback was attempted: {exc}")
        return 2
    print("MIGRATED: removed the managed default role and installed Codex-native defaults.")
    return 0


def command_uninstall(codex_home: Path, args: argparse.Namespace) -> int:
    if not args.apply:
        print("ERROR: uninstall requires --apply.")
        return 2
    state_path = codex_home / STATE_NAME
    try:
        state = load_state(state_path)
        if state is None:
            print("ERROR: no managed installation record exists.")
            return 1
        if not state_is_current(codex_home, state):
            print("BLOCKED: a managed file changed after installation; preserve it and restore manually.")
            return 1
        originals = originals_from_state(codex_home, state)
    except (ConfigError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2
    current = {path: read_optional(path) for path in originals}
    try:
        for path, original in originals.items():
            restore_bytes(path, original)
        state_path.unlink()
    except OSError as exc:
        for path, data in current.items():
            restore_bytes(path, data)
        print(f"ERROR: restore failed and rollback was attempted: {exc}")
        return 2
    print("RESTORED: pre-install managed file state.")
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
    if args.command == "migrate":
        return command_migrate(codex_home, args)
    return command_uninstall(codex_home, args)


if __name__ == "__main__":
    sys.exit(main())
