"""Observe set_key return values, exact file bytes and bounded exception recovery.

Source-only runner for a reviewed checkout. It executes trusted Python code,
requires a fresh process and a new disposable scratch directory, and retains
all resulting synthetic files. It does not test power-loss durability.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
FILES = ["__init__.py", "cli.py", "ipython.py", "main.py",
         "parser.py", "variables.py", "version.py"]
MODULES = ["dotenv", "dotenv.main", "dotenv.parser", "dotenv.variables"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, expected):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != expected:
        raise ValueError("Input size or caller-supplied digest differs")
    return json.loads(raw)


def validate(manifest, oracle):
    if set(manifest) != {"schema_version", "cases"} or manifest["schema_version"] != 1:
        raise ValueError("Unknown manifest schema")
    if not isinstance(manifest["cases"], list) or not 1 <= len(manifest["cases"]) <= 32:
        raise ValueError("Expected bounded cases")
    ids = set()
    for c in manifest["cases"]:
        if set(c) != {"id", "before", "key", "value", "quote_mode", "export", "fault"}:
            raise ValueError("Unknown or missing setting")
        if not isinstance(c["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", c["id"]) or c["id"] in ids:
            raise ValueError("Invalid or duplicate case ID")
        ids.add(c["id"])
        if any(not isinstance(c[k], str) or len(c[k]) > 4096 for k in ("before", "key", "value")):
            raise ValueError("Expected bounded text")
        if not re.fullmatch(r"X36_[A-Z]+", c["key"]):
            raise ValueError("Use synthetic key names")
        if c["quote_mode"] not in ("always", "never") or type(c["export"]) is not bool:
            raise ValueError("Unknown mode")
        if c["fault"] not in ("none", "after_first_binding"):
            raise ValueError("Unknown fault")
    if set(oracle) != {"schema_version", "expected"} or oracle["schema_version"] != 1:
        raise ValueError("Unknown oracle schema")
    if set(oracle["expected"]) != ids:
        raise ValueError("Oracle and case IDs differ")
    for value in oracle["expected"].values():
        if set(value) != {"return", "exception", "after_posix", "after_windows", "temp_files"}:
            raise ValueError("Unknown oracle field")
        if not all(isinstance(value[k], str) for k in ("after_posix", "after_windows")):
            raise ValueError("Expected literal output text")
        if value["exception"] not in (None, "InjectedWriteError") or value["temp_files"] != []:
            raise ValueError("Unsupported expected outcome")
        if value["return"] is not None and (
            not isinstance(value["return"], list) or len(value["return"]) != 3
            or value["return"][0] is not True
            or not all(isinstance(x, str) for x in value["return"][1:])
        ):
            raise ValueError("Invalid expected return")


def capture_scope(repo):
    folder = repo / "src/dotenv"
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.py"))
    if names != sorted(FILES) or any(folder.rglob("*.pyc")) or any(folder.rglob("*.pyo")):
        raise ValueError("Unexpected package inventory or bytecode")
    scope = {}
    for name in names:
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError("Package source escapes checkout")
        scope["src/dotenv/" + name] = digest(path.read_bytes())
    return scope


class InjectedWriteError(Exception):
    pass


def run_case(module, case, expected, scratch):
    folder = scratch / case["id"]
    folder.mkdir()
    temp = folder / "temp"
    temp.mkdir()
    target = folder / "target.env"
    target.write_bytes(case["before"].encode("utf-8"))
    before = target.read_bytes()
    original_parser = module.parse_stream
    fault_hits = []

    def injected(stream):
        for binding in original_parser(stream):
            yield binding
            fault_hits.append("after_first_binding")
            raise InjectedWriteError()

    returned, error = None, None
    parser = injected if case["fault"] != "none" else original_parser
    with patch.object(tempfile, "tempdir", str(temp)), patch.object(module, "parse_stream", parser):
        try:
            returned = list(module.set_key(str(target), case["key"], case["value"],
                                           quote_mode=case["quote_mode"], export=case["export"]))
        except InjectedWriteError:
            error = "InjectedWriteError"
    if case["fault"] != "none" and fault_hits != ["after_first_binding"]:
        raise ValueError("Required fault point was not reached exactly once")
    after = target.read_bytes()
    remaining = sorted(p.name for p in temp.iterdir())
    wanted = expected["after_windows" if os.name == "nt" else "after_posix"].encode("utf-8")
    outcome_ok = returned == expected["return"] and error == expected["exception"]
    artifact_ok = after == wanted and remaining == expected["temp_files"]
    return {
        "id": case["id"], "return": returned, "exception": error,
        "fault_hits": fault_hits, "before": before.decode("utf-8"),
        "after": after.decode("utf-8"), "before_sha256": digest(before),
        "after_sha256": digest(after), "temp_files": remaining,
        "outcome_status": "PASS" if outcome_ok else "FAIL",
        "artifact_status": "PASS" if artifact_ok else "FAIL",
        "status": "PASS" if outcome_ok and artifact_ok else "FAIL",
    }


def run(repo, manifest, oracle, scratch):
    validate(manifest, oracle)
    repo = repo.resolve()
    before_scope = capture_scope(repo)
    if any(name == "dotenv" or name.startswith("dotenv.") for name in sys.modules):
        raise ValueError("Use a fresh process")
    # Refuse existing scratch content; never remove, reuse or repair it.
    if scratch.exists() or scratch.is_symlink() or not scratch.parent.is_dir():
        raise ValueError("Scratch must be a new directory with an existing parent")
    scratch.mkdir()
    scratch = scratch.resolve()
    canary = scratch / "canary.txt"
    canary.write_bytes(b"X36 unrelated synthetic content\n")
    sys.path.insert(0, str(repo / "src"))
    import dotenv.main as module
    origins = {}
    for name in MODULES:
        path = Path(sys.modules[name].__file__).resolve()
        if not path.is_relative_to(repo / "src/dotenv"):
            raise ValueError("Imported module escapes reviewed package")
        origins[name] = path.relative_to(repo).as_posix()
    tests = [run_case(module, case, oracle["expected"][case["id"]], scratch)
             for case in manifest["cases"]]
    if canary.read_bytes() != b"X36 unrelated synthetic content\n":
        raise ValueError("Unrelated synthetic content changed")
    if capture_scope(repo) != before_scope:
        raise ValueError("Code changed during execution")
    return {
        "code_scope": before_scope, "module_origins": origins,
        "runtime": {"python": platform.python_version(), "platform": sys.platform},
        "tests": tests, "canary_unchanged": True,
        "scratch_retained": True, "crash_durability_tested": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--oracle-sha256", required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = read_pinned(args.manifest, args.manifest_sha256)
    oracle = read_pinned(args.oracle, args.oracle_sha256)
    report = run(args.repo, manifest, oracle, args.scratch)
    report.update(manifest_sha256=args.manifest_sha256, oracle_sha256=args.oracle_sha256,
                  probe_sha256=digest(Path(__file__).read_bytes()))
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if all(t["status"] == "PASS" for t in report["tests"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
