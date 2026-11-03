#!/usr/bin/env python3
"""Prepare exact pinned Git blobs in a new directory; dry-run by default."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from install_luna_skills import (
    InstallError, _absolute, _assert_directory,
    _assert_existing_path_chain_is_direct, _is_within, _lexists,
)
from read_evidence import encode, load_json, pin

MAX_MANIFEST = 65536
MAX_FILES = 64
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
OID = re.compile(r"[0-9a-f]{40}")
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

def git_environment():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1",
               GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    return env

def git(repo, *args):
    run = subprocess.run(
        ["git", "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo),
         "-c", "core.fsmonitor=false", *args],
        env=git_environment(), capture_output=True, timeout=30,
    )
    if run.returncode:
        raise ValueError("Git operation failed: " + args[0])
    return run.stdout

def portable_path(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        raise ValueError("Invalid bounded relative path")
    parts = value.split("/")
    if len(parts) > 16:
        raise ValueError("Path too deep")
    for part in parts:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") or part.endswith(".") or part.lower() == ".git" or part.split(".", 1)[0].upper() in RESERVED:
            raise ValueError("Path is not portable or direct")
    return parts

def validate(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "commit", "files"} or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unknown manifest schema")
    if not isinstance(manifest["commit"], str) or not OID.fullmatch(manifest["commit"]):
        raise ValueError("Expected full SHA1 commit ID")
    rows = manifest["files"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise ValueError("Expected 1 to 64 files")
    leaves, prefixes, total = set(), {}, 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "bytes", "mode"}:
            raise ValueError("Unknown file fields")
        parts = portable_path(row["path"])
        if row["path"].lower() in leaves:
            raise ValueError("Duplicate file path")
        leaves.add(row["path"].lower())
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            if prefix.lower() in prefixes and prefixes[prefix.lower()] != prefix:
                raise ValueError("Case-colliding path components")
            prefixes[prefix.lower()] = prefix
        pin(row["sha256"])
        if type(row["bytes"]) is not int or not 0 <= row["bytes"] <= MAX_FILE_BYTES:
            raise ValueError("Invalid file size")
        total += row["bytes"]
        if row["mode"] not in ("100644", "100755"):
            raise ValueError("Only regular Git file modes are supported")
    if total > MAX_TOTAL_BYTES:
        raise ValueError("Total byte limit exceeded")
    for row in rows:
        parts = row["path"].lower().split("/")
        if any("/".join(parts[:index]) in leaves for index in range(1, len(parts))):
            raise ValueError("File and directory paths overlap")
    return sorted(rows, key=lambda row: row["path"])

def load_manifest(path, expected):
    pin(expected)
    _assert_existing_path_chain_is_direct(path, label="manifest")
    if not stat.S_ISREG(Path(path).lstat().st_mode):
        raise ValueError("Manifest must be an ordinary file")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_MANIFEST + 1)
    if len(raw) > MAX_MANIFEST or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Manifest size or independent pin differs")
    data = load_json(raw)
    return data, validate(data)

def prepare(repo, manifest_path, expected, target, *, apply=False):
    created = False
    completed = []
    try:
        manifest, rows = load_manifest(manifest_path, expected)
        repo, target = _absolute(repo), _absolute(target)
        _assert_existing_path_chain_is_direct(repo, label="repository")
        _assert_directory(repo, label="repository")
        _assert_existing_path_chain_is_direct(target, label="target")
        _assert_directory(target.parent, label="target parent")
        if _lexists(target):
            raise ValueError("Target already exists; no overwrite or reuse")
        actual_root = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel")).strip())
        if actual_root.resolve() != repo.resolve():
            raise ValueError("Repository must be its working-tree root")
        protected = [repo]
        for args in (("rev-parse", "--absolute-git-dir"), ("rev-parse", "--path-format=absolute", "--git-common-dir")):
            protected.append(Path(os.fsdecode(git(repo, *args)).strip()))
        if any(_is_within(target, parent) for parent in protected):
            raise ValueError("Target overlaps source repository or Git metadata")
        commit = manifest["commit"]
        if git(repo, "cat-file", "-t", commit).strip() != b"commit":
            raise ValueError("Pinned object is not a commit")
        payloads = []
        inventory = []
        for row in rows:
            tree = git(repo, "ls-tree", "-z", commit, "--", row["path"]).split(b"\0")
            if len(tree) != 2 or tree[-1] != b"":
                raise ValueError("Expected one exact tree entry")
            meta, path = tree[0].split(b"\t", 1)
            mode, kind, oid = meta.decode("ascii").split(" ")
            if path.decode("utf-8") != row["path"] or mode != row["mode"] or kind != "blob" or not OID.fullmatch(oid):
                raise ValueError("Tree entry is missing, indirect or has a different mode")
            size = int(git(repo, "cat-file", "-s", oid).strip())
            if size != row["bytes"]:
                raise ValueError("Pinned blob size differs")
            raw = git(repo, "cat-file", "blob", oid)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("Pinned blob content differs")
            payloads.append((row, raw))
            inventory.append(dict(row, git_blob=oid))
        result = {"schema_version": 1, "status": "PLAN", "commit": commit,
                  "manifest_sha256": expected, "files": inventory,
                  "total_bytes": sum(row["bytes"] for row in rows), "target_created": False}
        if not apply:
            return result
        # Stable, single-writer paths are required; this is not a race sandbox.
        _assert_existing_path_chain_is_direct(target.parent, label="target parent")
        target.mkdir()
        created = True
        for row, raw in payloads:
            dest = target.joinpath(*row["path"].split("/"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            _assert_existing_path_chain_is_direct(dest.parent, label="output parent")
            with dest.open("xb") as stream:
                stream.write(raw)
            if os.name != "nt":
                dest.chmod(0o755 if row["mode"] == "100755" else 0o644)
            completed.append(row["path"])
        for row, raw in payloads:
            dest = target.joinpath(*row["path"].split("/"))
            _assert_existing_path_chain_is_direct(dest, label="output")
            if dest.read_bytes() != raw:
                raise ValueError("Output readback differs")
        result.update(status="EXPORTED", target_created=True)
        return result
    except (OSError, ValueError, TypeError, RecursionError, InstallError, subprocess.SubprocessError) as error:
        return {"schema_version": 1, "status": "INCOMPLETE" if created else "REFUSED",
                "error": str(error), "target_created": created, "completed_files": completed}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="independently reviewed manifest digest")
    parser.add_argument("--target", type=Path, required=True, help="nonexistent directory under an existing direct parent")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = prepare(args.repo, args.manifest, args.sha256, args.target, apply=args.apply)
    sys.stdout.write(encode(result).decode("utf-8"))
    return 0 if result["status"] in ("PLAN", "EXPORTED") else 2

if __name__ == "__main__":
    raise SystemExit(main())
