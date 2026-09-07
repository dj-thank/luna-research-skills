from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_ROOT = Path.home() / ".agents" / "skills"
MAX_SKILLS = 64
MAX_SOURCE_ROOT_ENTRIES = 256
MAX_ENTRIES_PER_SKILL = 10_000
MAX_FILES_PER_SKILL = 5_000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_BYTES_PER_SKILL = 128 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 256 * 1024 * 1024
WINDOWS_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
DARWIN_SYSTEM_ALIASES = {
    Path("/etc"): Path("/private/etc"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/var"): Path("/private/var"),
}
IGNORED_DIRECTORY_NAMES = {"__pycache__"}
IGNORED_FILE_SUFFIXES = {".pyc", ".pyo"}
SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FRONTMATTER = re.compile(
    r"\A\ufeff?---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


class InstallError(RuntimeError):
    """A predictable validation or installation failure."""


def default_source(root: Path = REPOSITORY_ROOT) -> Path:
    """Select repository layout first, then the installable plugin layout."""
    repository_source = root / ".agents" / "skills"
    plugin_source = root / "skills"
    if os.path.lexists(repository_source):
        return repository_source
    if os.path.lexists(plugin_source):
        return plugin_source
    return repository_source


DEFAULT_SOURCE = default_source()


@dataclass(frozen=True)
class FileSnapshot:
    relative_path: str
    content: bytes
    sha256: str
    mode: int


@dataclass(frozen=True)
class SkillSnapshot:
    name: str
    source_path: Path
    files: tuple[FileSnapshot, ...]
    total_bytes: int

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass(frozen=True)
class InstallPlan:
    source_root: Path
    target_root: Path
    skills: tuple[SkillSnapshot, ...]


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _is_reparse_or_symlink(path: Path, *, st: os.stat_result | None = None) -> bool:
    details = st if st is not None else os.lstat(path)
    return stat.S_ISLNK(details.st_mode) or bool(
        getattr(details, "st_file_attributes", 0) & WINDOWS_REPARSE_POINT
    )


def _identity(details: os.stat_result) -> tuple[int | None, int | None]:
    return (getattr(details, "st_dev", None), getattr(details, "st_ino", None))


def _is_allowed_platform_alias(path: Path, details: os.stat_result) -> bool:
    """Allow only macOS's root-owned /etc, /tmp, and /var aliases."""
    expected = DARWIN_SYSTEM_ALIASES.get(path)
    if sys.platform != "darwin" or expected is None:
        return False
    if not stat.S_ISLNK(details.st_mode) or getattr(details, "st_uid", 0) != 0:
        return False
    try:
        return path.resolve(strict=True) == expected and expected.is_dir()
    except OSError:
        return False


def _assert_existing_path_chain_is_direct(path: Path, *, label: str) -> None:
    absolute = _absolute(path)
    chain: list[Path] = []
    cursor = absolute
    while True:
        chain.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent

    for candidate in reversed(chain):
        if not _lexists(candidate):
            continue
        details = os.lstat(candidate)
        if _is_reparse_or_symlink(candidate, st=details):
            if _is_allowed_platform_alias(candidate, details):
                continue
            raise InstallError(
                f"{label} contains a symlink, junction, or reparse point: {candidate}"
            )
        if candidate != absolute and not stat.S_ISDIR(details.st_mode):
            raise InstallError(f"{label} has a non-directory parent component: {candidate}")


def _assert_directory(path: Path, *, label: str) -> None:
    if not _lexists(path):
        raise InstallError(f"{label} does not exist: {path}")
    details = os.lstat(path)
    if _is_reparse_or_symlink(path, st=details):
        raise InstallError(f"{label} must not be a symlink, junction, or reparse point: {path}")
    if not stat.S_ISDIR(details.st_mode):
        raise InstallError(f"{label} is not a directory: {path}")


def _is_within(candidate: Path, parent: Path) -> bool:
    # Compare canonical locations as well as validating each visible path component.
    candidate_norm = os.path.normcase(os.path.realpath(_absolute(candidate)))
    parent_norm = os.path.normcase(os.path.realpath(_absolute(parent)))
    try:
        return os.path.commonpath([candidate_norm, parent_norm]) == parent_norm
    except ValueError:
        return False


def _assert_non_overlapping(source_root: Path, target_root: Path) -> None:
    if _is_within(source_root, target_root) or _is_within(target_root, source_root):
        raise InstallError(
            "source and target roots must not contain one another: "
            f"source={source_root}, target={target_root}"
        )


def _frontmatter_value(body: str, key: str) -> str | None:
    matches = re.findall(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*:[ \t]*(.+?)[ \t]*$", body)
    if len(matches) != 1:
        return None
    return matches[0].strip().strip("\"'")


def _read_regular_file(path: Path, relative_path: str) -> FileSnapshot:
    before = os.lstat(path)
    if _is_reparse_or_symlink(path, st=before):
        raise InstallError(f"source contains a symlink, junction, or reparse point: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise InstallError(f"source contains a non-regular file: {path}")
    if before.st_size > MAX_FILE_BYTES:
        raise InstallError(f"source file exceeds {MAX_FILE_BYTES} bytes: {path}")

    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise InstallError(f"source changed to a non-regular file while reading: {path}")
            if _identity(before) != _identity(opened):
                raise InstallError(f"source changed while opening: {path}")
            content = handle.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise InstallError(f"cannot read source file {path}: {exc}") from exc

    if len(content) > MAX_FILE_BYTES:
        raise InstallError(f"source file exceeds {MAX_FILE_BYTES} bytes: {path}")

    after = os.lstat(path)
    if _is_reparse_or_symlink(path, st=after) or _identity(after) != _identity(opened):
        raise InstallError(f"source changed while reading: {path}")

    return FileSnapshot(
        relative_path=relative_path,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        mode=(stat.S_IMODE(opened.st_mode) & 0o755) | 0o600,
    )


def _snapshot_package_files(package: Path) -> tuple[tuple[FileSnapshot, ...], int]:
    package = _absolute(package)
    _assert_existing_path_chain_is_direct(package, label="source package path")
    _assert_directory(package, label="source package")

    pending = [package]
    snapshots: list[FileSnapshot] = []
    total_bytes = 0
    entry_count = 0
    collision_keys: set[str] = set()

    while pending:
        directory = pending.pop()
        _assert_directory(directory, label="source package directory")
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise InstallError(f"cannot enumerate source directory {directory}: {exc}") from exc

        for entry in entries:
            entry_count += 1
            if entry_count > MAX_ENTRIES_PER_SKILL:
                raise InstallError(
                    f"source package exceeds {MAX_ENTRIES_PER_SKILL} entries: {package}"
                )
            path = Path(entry.path)
            relative = path.relative_to(package).as_posix()
            try:
                details = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise InstallError(f"cannot inspect source entry {path}: {exc}") from exc

            if _is_reparse_or_symlink(path, st=details):
                raise InstallError(f"source contains a symlink, junction, or reparse point: {path}")

            collision_key = relative.casefold()
            if collision_key in collision_keys:
                raise InstallError(f"source has a case-insensitive path collision: {relative}")
            collision_keys.add(collision_key)

            if stat.S_ISDIR(details.st_mode):
                if entry.name not in IGNORED_DIRECTORY_NAMES:
                    pending.append(path)
                continue
            if not stat.S_ISREG(details.st_mode):
                raise InstallError(f"source contains a non-regular file: {path}")
            if path.suffix.lower() in IGNORED_FILE_SUFFIXES:
                continue

            snapshots.append(_read_regular_file(path, relative))
            if len(snapshots) > MAX_FILES_PER_SKILL:
                raise InstallError(
                    f"source package exceeds {MAX_FILES_PER_SKILL} files: {package}"
                )
            total_bytes += len(snapshots[-1].content)
            if total_bytes > MAX_BYTES_PER_SKILL:
                raise InstallError(
                    f"source package exceeds {MAX_BYTES_PER_SKILL} bytes: {package}"
                )

    snapshots.sort(key=lambda item: item.relative_path.casefold())
    return tuple(snapshots), total_bytes


def _snapshot_skill(package: Path) -> SkillSnapshot:
    package = _absolute(package)
    snapshots, total_bytes = _snapshot_package_files(package)
    by_path = {item.relative_path: item for item in snapshots}
    skill_file = by_path.get("SKILL.md")
    if skill_file is None:
        raise InstallError(f"source package is missing SKILL.md: {package}")
    try:
        skill_text = skill_file.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError(f"SKILL.md is not valid UTF-8: {package / 'SKILL.md'}") from exc

    frontmatter = FRONTMATTER.match(skill_text)
    if frontmatter is None:
        raise InstallError(
            f"SKILL.md is missing valid YAML frontmatter: {package / 'SKILL.md'}"
        )
    name = _frontmatter_value(frontmatter.group("body"), "name")
    description = _frontmatter_value(frontmatter.group("body"), "description")
    if not name or not SKILL_NAME.fullmatch(name):
        raise InstallError(
            f"SKILL.md has an invalid or duplicate name field: {package / 'SKILL.md'}"
        )
    if not description:
        raise InstallError(
            f"SKILL.md has a missing, empty, or duplicate description field: {package / 'SKILL.md'}"
        )
    if package.name != name:
        raise InstallError(
            f"skill directory {package.name!r} does not match frontmatter name {name!r}"
        )

    return SkillSnapshot(
        name=name,
        source_path=package,
        files=snapshots,
        total_bytes=total_bytes,
    )


def _discover_skills(source_root: Path) -> tuple[SkillSnapshot, ...]:
    _assert_existing_path_chain_is_direct(source_root, label="source root path")
    _assert_directory(source_root, label="source root")
    packages: list[Path] = []
    try:
        entries = sorted(
            os.scandir(source_root), key=lambda entry: entry.name.casefold()
        )
    except OSError as exc:
        raise InstallError(f"cannot enumerate source root {source_root}: {exc}") from exc

    if len(entries) > MAX_SOURCE_ROOT_ENTRIES:
        raise InstallError(
            f"source root exceeds {MAX_SOURCE_ROOT_ENTRIES} entries: {source_root}"
        )

    for entry in entries:
        path = Path(entry.path)
        details = entry.stat(follow_symlinks=False)
        if _is_reparse_or_symlink(path, st=details):
            raise InstallError(
                f"source root contains a symlink, junction, or reparse point: {path}"
            )
        if stat.S_ISDIR(details.st_mode):
            if entry.name in IGNORED_DIRECTORY_NAMES:
                continue
            if not (path / "SKILL.md").is_file():
                raise InstallError(
                    f"source root contains a directory without SKILL.md: {path}"
                )
            packages.append(path)
        elif stat.S_ISREG(details.st_mode):
            continue
        else:
            raise InstallError(f"source root contains a non-regular entry: {path}")

    if not packages:
        raise InstallError(f"source root contains no skill packages: {source_root}")
    if len(packages) > MAX_SKILLS:
        raise InstallError(f"source root exceeds {MAX_SKILLS} skill packages: {source_root}")

    skills = tuple(_snapshot_skill(package) for package in packages)
    total_source_bytes = sum(skill.total_bytes for skill in skills)
    if total_source_bytes > MAX_TOTAL_SOURCE_BYTES:
        raise InstallError(
            f"source root exceeds {MAX_TOTAL_SOURCE_BYTES} total bytes: {source_root}"
        )
    names: set[str] = set()
    for skill in skills:
        key = skill.name.casefold()
        if key in names:
            raise InstallError(f"source root contains duplicate skill name: {skill.name}")
        names.add(key)
    return skills


def build_plan(source_root: Path | str, target_root: Path | str) -> InstallPlan:
    source = _absolute(source_root)
    target = _absolute(target_root)
    _assert_non_overlapping(source, target)
    skills = _discover_skills(source)
    _assert_existing_path_chain_is_direct(target, label="target root path")
    if _lexists(target):
        details = os.lstat(target)
        if _is_reparse_or_symlink(target, st=details) or not stat.S_ISDIR(details.st_mode):
            raise InstallError(f"target root must be a direct directory: {target}")
    for skill in skills:
        destination = target / skill.name
        if _lexists(destination):
            raise InstallError(
                f"destination already exists; refusing to overwrite: {destination}"
            )
    return InstallPlan(source_root=source, target_root=target, skills=skills)


def _snapshot_signature(skill: SkillSnapshot) -> dict[str, str]:
    return {item.relative_path: item.sha256 for item in skill.files}


def _assert_matches(expected: SkillSnapshot, actual: SkillSnapshot, *, label: str) -> None:
    expected_signature = _snapshot_signature(expected)
    actual_signature = _snapshot_signature(actual)
    if expected.name != actual.name:
        raise InstallError(
            f"{label} skill name mismatch: expected {expected.name!r}, got {actual.name!r}"
        )
    if expected_signature != actual_signature:
        expected_paths = set(expected_signature)
        actual_paths = set(actual_signature)
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        changed = sorted(
            path
            for path in expected_paths & actual_paths
            if expected_signature[path] != actual_signature[path]
        )
        details = []
        if missing:
            details.append("missing=" + ",".join(missing[:5]))
        if extra:
            details.append("extra=" + ",".join(extra[:5]))
        if changed:
            details.append("changed=" + ",".join(changed[:5]))
        raise InstallError(f"{label} content mismatch ({'; '.join(details) or 'unknown'})")


def verify_installation(source_root: Path | str, target_root: Path | str) -> InstallPlan:
    source = _absolute(source_root)
    target = _absolute(target_root)
    _assert_non_overlapping(source, target)
    skills = _discover_skills(source)
    _assert_existing_path_chain_is_direct(target, label="target root path")
    _assert_directory(target, label="target root")
    for skill in skills:
        destination = target / skill.name
        actual = _snapshot_skill(destination)
        _assert_matches(skill, actual, label=f"installed package {skill.name}")
    return InstallPlan(source_root=source, target_root=target, skills=skills)


def _ensure_direct_directory(path: Path) -> list[Path]:
    absolute = _absolute(path)
    _assert_existing_path_chain_is_direct(absolute, label="destination path")
    missing: list[Path] = []
    cursor = absolute
    while not _lexists(cursor):
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent

    created: list[Path] = []
    try:
        for directory in reversed(missing):
            try:
                directory.mkdir()
                created.append(directory)
            except FileExistsError:
                pass
            _assert_directory(directory, label="destination directory")
            _assert_existing_path_chain_is_direct(directory, label="destination path")
        return created
    except BaseException:
        for directory in reversed(created):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise


def _ensure_owned_subdirectory(package_root: Path, relative_parent: Path) -> Path:
    cursor = package_root
    for part in relative_parent.parts:
        cursor = cursor / part
        try:
            cursor.mkdir()
        except FileExistsError:
            details = os.lstat(cursor)
            if _is_reparse_or_symlink(cursor, st=details) or not stat.S_ISDIR(details.st_mode):
                raise InstallError(f"destination path was replaced during installation: {cursor}")
    return cursor


def _reserve_destination(destination: Path) -> None:
    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise InstallError(
            f"destination already exists; refusing to overwrite: {destination}"
        ) from exc
    except OSError as exc:
        raise InstallError(f"cannot reserve destination {destination}: {exc}") from exc
    _assert_directory(destination, label="reserved destination")


def _write_reserved_skill(destination: Path, skill: SkillSnapshot) -> None:
    # Write SKILL.md after every supporting file to minimize exposure of a partial package.
    ordered = sorted(
        skill.files,
        key=lambda item: (item.relative_path == "SKILL.md", item.relative_path.casefold()),
    )
    for snapshot in ordered:
        relative = Path(*snapshot.relative_path.split("/"))
        parent = _ensure_owned_subdirectory(destination, relative.parent)
        output = parent / relative.name
        try:
            with output.open("xb") as handle:
                handle.write(snapshot.content)
                handle.flush()
                os.fsync(handle.fileno())
            if os.name != "nt":
                os.chmod(output, snapshot.mode)
        except OSError as exc:
            raise InstallError(
                f"cannot install {skill.name}/{snapshot.relative_path}: {exc}"
            ) from exc

    actual = _snapshot_skill(destination)
    _assert_matches(skill, actual, label=f"installed package {skill.name}")


def _rollback_inventory(
    path: Path, expected: SkillSnapshot
) -> tuple[list[tuple[Path, FileSnapshot]], list[Path]]:
    """Inventory every entry before rollback; ignored source artifacts are not ignored here."""
    _assert_existing_path_chain_is_direct(path, label="rollback package path")
    _assert_directory(path, label="rollback package")
    expected_signature = _snapshot_signature(expected)
    pending = [path]
    directories = [path]
    actual_files: list[tuple[Path, FileSnapshot]] = []
    entry_count = 0

    while pending:
        directory = pending.pop()
        _assert_directory(directory, label="rollback package directory")
        try:
            entries = sorted(
                os.scandir(directory), key=lambda entry: entry.name.casefold()
            )
        except OSError as exc:
            raise InstallError(
                f"cannot enumerate rollback directory {directory}: {exc}"
            ) from exc

        for entry in entries:
            entry_count += 1
            if entry_count > MAX_ENTRIES_PER_SKILL:
                raise InstallError(
                    f"rollback package exceeds {MAX_ENTRIES_PER_SKILL} entries: {path}"
                )
            entry_path = Path(entry.path)
            relative = entry_path.relative_to(path).as_posix()
            try:
                details = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise InstallError(
                    f"cannot inspect rollback entry {entry_path}: {exc}"
                ) from exc
            if _is_reparse_or_symlink(entry_path, st=details):
                raise InstallError(
                    "rollback found a symlink, junction, or reparse point: "
                    f"{relative}"
                )
            if stat.S_ISDIR(details.st_mode):
                directories.append(entry_path)
                pending.append(entry_path)
                continue
            if not stat.S_ISREG(details.st_mode):
                raise InstallError(f"rollback found a non-regular entry: {relative}")

            snapshot = _read_regular_file(entry_path, relative)
            expected_hash = expected_signature.get(relative)
            if expected_hash is None:
                raise InstallError(f"rollback found an unexpected file: {relative}")
            if expected_hash != snapshot.sha256:
                raise InstallError(f"rollback found a modified file: {relative}")
            actual_files.append((entry_path, snapshot))

    return actual_files, directories


def _remove_owned_package(path: Path, expected: SkillSnapshot) -> None:
    actual_files, directories = _rollback_inventory(path, expected)
    # Unpublish first, then remove only files observed with their expected bytes.
    actual_files.sort(
        key=lambda item: (
            item[1].relative_path != "SKILL.md",
            -len(Path(item[1].relative_path).parts),
            item[1].relative_path.casefold(),
        )
    )
    for file_path, observed in actual_files:
        current = _read_regular_file(file_path, observed.relative_path)
        if current.sha256 != observed.sha256:
            raise InstallError(
                f"rollback found a modified file: {observed.relative_path}"
            )
        try:
            file_path.unlink()
        except OSError as exc:
            raise InstallError(
                f"cannot remove rollback file {observed.relative_path}: {exc}"
            ) from exc

    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError as exc:
            raise InstallError(
                f"rollback directory is not empty or changed: {directory}: {exc}"
            ) from exc


def _remove_created_directories(created: list[Path]) -> list[str]:
    failures: list[str] = []
    for directory in reversed(created):
        try:
            directory.rmdir()
        except OSError as exc:
            # Non-empty directories are preserved; this may include concurrent user work.
            failures.append(f"{directory}: {exc}")
    return failures


def install_skills(plan: InstallPlan) -> InstallPlan:
    # Re-run all non-mutating checks immediately before creating any destination.
    current_plan = build_plan(plan.source_root, plan.target_root)
    if tuple(skill.name for skill in current_plan.skills) != tuple(
        skill.name for skill in plan.skills
    ):
        raise InstallError("source skill inventory changed after planning")
    for expected, current in zip(plan.skills, current_plan.skills, strict=True):
        _assert_matches(expected, current, label=f"source package {expected.name}")

    target = plan.target_root
    created_directories = _ensure_direct_directory(target)
    created_packages: list[tuple[Path, SkillSnapshot]] = []
    rollback_failures: list[str] = []
    try:
        # Recheck all names before writing, then reserve each final directory with mkdir.
        for skill in plan.skills:
            destination = target / skill.name
            if _lexists(destination):
                raise InstallError(
                    "destination appeared before installation; refusing to overwrite: "
                    f"{destination}"
                )

        for skill in plan.skills:
            destination = target / skill.name
            _reserve_destination(destination)
            created_packages.append((destination, skill))
            _write_reserved_skill(destination, skill)
        return plan
    except BaseException as exc:
        for destination, skill in reversed(created_packages):
            if not _lexists(destination):
                continue
            try:
                _remove_owned_package(destination, skill)
            except Exception as rollback_exc:  # preserve user-modified data over cleanup
                rollback_failures.append(f"{destination}: {rollback_exc}")
        rollback_failures.extend(_remove_created_directories(created_directories))
        if rollback_failures:
            detail = " | ".join(rollback_failures)
            raise InstallError(
                f"installation failed and rollback left paths for manual inspection: {detail}; "
                f"original error: {exc}"
            ) from exc
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(exc, InstallError):
            raise
        raise InstallError(f"installation failed: {exc}") from exc


def _payload(
    mode: str,
    status: str,
    plan: InstallPlan | None,
    message: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {"mode": mode, "status": status}
    if message:
        result["message"] = message
    if plan is not None:
        result.update(
            {
                "source_root": os.fspath(plan.source_root),
                "target_root": os.fspath(plan.target_root),
                "skills": [
                    {
                        "name": skill.name,
                        "files": skill.file_count,
                        "bytes": skill.total_bytes,
                    }
                    for skill in plan.skills
                ],
            }
        )
    return result


def _print_payload(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    status = payload["status"]
    mode = payload["mode"]
    if status == "ERROR":
        print(f"ERROR: {payload.get('message', 'unknown error')}", file=sys.stderr)
        return
    print(f"{status}: mode={mode} target={payload.get('target_root')}")
    for skill in payload.get("skills", []):
        assert isinstance(skill, dict)
        print(f"  - {skill['name']}: {skill['files']} files, {skill['bytes']} bytes")
    if mode == "plan":
        print("No files changed. Re-run with --apply to install new packages.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely install this repository's Codex skills into the user scope. "
            "The default mode is a non-mutating plan; existing packages are never overwritten."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"skill source root (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=DEFAULT_TARGET_ROOT,
        help="user skill root (default: $HOME/.agents/skills)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="perform a new installation")
    mode.add_argument("--verify", action="store_true", help="verify an existing installation")
    parser.add_argument("--json", action="store_true", help="emit one machine-readable JSON object")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected_mode = "verify" if args.verify else "apply" if args.apply else "plan"
    try:
        if args.verify:
            plan = verify_installation(args.source, args.target_root)
            payload = _payload(selected_mode, "VERIFIED", plan)
        else:
            plan = build_plan(args.source, args.target_root)
            if args.apply:
                install_skills(plan)
                payload = _payload(selected_mode, "INSTALLED", plan)
            else:
                payload = _payload(selected_mode, "PLAN", plan)
        _print_payload(payload, as_json=args.json)
        return 0
    except (InstallError, OSError, UnicodeError) as exc:
        _print_payload(
            _payload(selected_mode, "ERROR", None, str(exc)),
            as_json=args.json,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
