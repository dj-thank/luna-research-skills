"""Run the fixed dotenv task in a trusted checkout with synthetic inputs only.

No downloads, installation, file discovery or host environment export. A fresh
process is required: the selected package is imported and executes Python code.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
FILES = ["__init__.py", "cli.py", "compat.py", "ipython.py", "main.py",
         "parser.py", "variables.py", "version.py"]
MODULES = ["dotenv", "dotenv.compat", "dotenv.main", "dotenv.parser", "dotenv.variables"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, expected):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != expected:
        raise ValueError("Input is oversized or differs from its caller-supplied pin")
    return json.loads(raw)


def validate(manifest, oracle):
    if set(manifest) != {"schema_version", "cases"} or manifest["schema_version"] != 1:
        raise ValueError("Unknown manifest schema")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise ValueError("Expected a bounded case list")
    seen = set()
    for case in cases:
        if set(case) != {"id", "dotenv", "environment", "override", "interpolate"}:
            raise ValueError("Unknown or missing execution setting")
        name = case["id"]
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Case IDs must be unique strings")
        seen.add(name)
        if not isinstance(case["dotenv"], str) or not isinstance(case["environment"], dict):
            raise ValueError("Expected text input and an explicit environment")
        if any(not isinstance(k, str) or not k.startswith("X35_") or not isinstance(v, str)
               for k, v in case["environment"].items()):
            raise ValueError("Only synthetic X35_ environment values are supported")
        if type(case["override"]) is not bool or type(case["interpolate"]) is not bool:
            raise ValueError("Mode flags must be booleans")
    if set(oracle) != {"schema_version", "expected"} or oracle["schema_version"] != 1:
        raise ValueError("Unknown oracle schema")
    if set(oracle["expected"]) != seen:
        raise ValueError("Oracle and manifest case IDs differ")
    for expected in oracle["expected"].values():
        if not isinstance(expected, dict) or set(expected) != {"environment", "return"}:
            raise ValueError("Invalid expected result")
        if not isinstance(expected["environment"], dict) or type(expected["return"]) is not bool:
            raise ValueError("Expected environment map and boolean result")
        if any(not isinstance(k, str) or not k.startswith("X35_") or not isinstance(v, str)
               for k, v in expected["environment"].items()):
            raise ValueError("Oracle values must be synthetic strings")


def capture_scope(repo):
    folder = repo / "src/dotenv"
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.py"))
    if files != sorted(FILES) or any(folder.rglob("*.pyc")) or any(folder.rglob("*.pyo")):
        raise ValueError("Use the reviewed package inventory without bytecode caches")
    result = {}
    for name in files:
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError("Package source escapes the checkout")
        result["src/dotenv/" + name] = digest(path.read_bytes())
    return result


def run_cases(load, manifest, oracle):
    validate(manifest, oracle)
    rows = []
    for case in manifest["cases"]:
        expected = oracle["expected"][case["id"]]
        # This process-local scope contains only fabricated fixture values.
        # Never serialize the host environment captured internally by patch.dict.
        with patch.dict(os.environ, case["environment"], clear=True):
            try:
                returned = load(stream=io.StringIO(case["dotenv"]),
                                override=case["override"], interpolate=case["interpolate"])
                actual = {"return": returned, "environment": dict(os.environ)}
                status = "PASS" if actual == expected else "FAIL"
            except Exception as exc:
                actual = {"error_type": type(exc).__name__}
                status = "ERROR"
        rows.append({"id": case["id"], "status": status, "actual": actual})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--oracle-sha256", required=True)
    args = parser.parse_args()
    manifest = read_pinned(args.manifest, args.manifest_sha256)
    oracle = read_pinned(args.oracle, args.oracle_sha256)
    validate(manifest, oracle)
    repo = args.repo.resolve(strict=True)
    before = capture_scope(repo)
    sys.path.insert(0, str(repo / "src"))
    import dotenv
    origins = {}
    for name in MODULES:
        relative = "src/dotenv/" + ("__init__.py" if name == "dotenv" else name.split(".")[-1] + ".py")
        module = sys.modules.get(name)
        if module is None or Path(module.__file__).resolve() != (repo / relative).resolve():
            raise ValueError("Imported origin differs from the reviewed package")
        origins[name] = relative
    rows = run_cases(dotenv.load_dotenv, manifest, oracle)
    if capture_scope(repo) != before:
        raise ValueError("Package source changed during execution")
    # Recheck the exact raw fixture bytes, not merely their parsed JSON values.
    read_pinned(args.manifest, args.manifest_sha256)
    read_pinned(args.oracle, args.oracle_sha256)
    report = {"schema_version": 1, "task": "python-dotenv-282", "code_scope": before,
              "module_origins": origins, "manifest_sha256": args.manifest_sha256,
              "oracle_sha256": args.oracle_sha256, "probe_sha256": digest(Path(__file__).read_bytes()),
              "runtime": {"python": platform.python_version(), "platform": sys.platform}, "tests": rows}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(row["status"] == "PASS" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
