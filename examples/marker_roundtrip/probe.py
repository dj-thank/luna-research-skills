"""Execute pinned packaging marker round trips with synthetic environments.

Trusted source-only execution. No packages, URLs or dependencies are installed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

sys.dont_write_bytecode = True
FILES = ["__init__.py", "_elffile.py", "_manylinux.py", "_musllinux.py", "_parser.py",
         "_ranges.py", "_structures.py", "_tokenizer.py", "dependency_groups.py",
         "direct_url.py", "errors.py", "licenses/__init__.py", "licenses/_spdx.py",
         "markers.py", "metadata.py", "pylock.py", "ranges.py", "requirements.py",
         "specifiers.py", "tags.py", "utils.py", "version.py"]
ENV_KEYS = {"implementation_name", "implementation_version", "os_name", "platform_machine",
            "platform_release", "platform_system", "platform_version", "python_full_version",
            "platform_python_implementation", "python_version", "sys_platform", "extra"}
FIELDS = {"before", "after", "initial_error", "serialization_error", "roundtrip_error"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, pin):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != pin:
        raise ValueError("Input size or independently supplied pin differs")
    return json.loads(raw)


def validate(manifest, oracle):
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "environment", "cases"} or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unknown manifest schema")
    env = manifest["environment"]
    if not isinstance(env, dict) or set(env) != ENV_KEYS or any(not isinstance(v, str) or len(v) > 2048 for v in env.values()):
        raise ValueError("Supply the complete bounded synthetic environment")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise ValueError("Expected bounded cases")
    if not isinstance(oracle, dict) or set(oracle) != {"schema_version", "expected"} or type(oracle["schema_version"]) is not int or oracle["schema_version"] != 1 or not isinstance(oracle["expected"], dict):
        raise ValueError("Unknown oracle schema")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "kind", "input", "overrides"}:
            raise ValueError("Unknown case fields")
        key = case["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) or key in seen:
            raise ValueError("Unsafe or duplicate case ID")
        seen.add(key)
        if case["kind"] not in ("marker", "requirement", "value") or not isinstance(case["input"], str) or len(case["input"]) > 2048:
            raise ValueError("Invalid case input")
        if not isinstance(case["overrides"], dict) or not set(case["overrides"]) <= ENV_KEYS or any(not isinstance(v, str) or len(v) > 2048 for v in case["overrides"].values()):
            raise ValueError("Invalid explicit environment overrides")
        expected = oracle["expected"].get(key)
        fields = FIELDS | ({"serialized"} if case["kind"] == "value" else set())
        if not isinstance(expected, dict) or set(expected) != fields:
            raise ValueError("Oracle must cover every required observation")
    if set(oracle["expected"]) != seen:
        raise ValueError("Oracle and manifest cases differ")


def capture_scope(repo):
    folder = repo / "src/packaging"
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.py"))
    if names != sorted(FILES) or any(folder.rglob("*.pyc")) or any(folder.rglob("*.pyo")):
        raise ValueError("Unexpected source inventory or bytecode cache")
    scope = {}
    for name in names:
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError("Source escapes checkout")
        scope["src/packaging/" + name] = digest(path.read_bytes())
    return scope


def literals(node, value_type):
    if isinstance(node, value_type):
        return [str(node)]
    if isinstance(node, (list, tuple)):
        return [value for child in node for value in literals(child, value_type)]
    return []


def observe(case, env, marker_type, requirement_type, value_type):
    result = {"before": None, "after": None, "serialized": None,
              "initial_error": None, "serialization_error": None, "roundtrip_error": None}
    kind = case["kind"]
    constructor = {"marker": marker_type, "requirement": requirement_type, "value": value_type}[kind]

    def snapshot(obj):
        if kind == "value":
            return {"literals": [str(obj)], "evaluation": None, "requirement": None}
        marker = obj.marker if kind == "requirement" else obj
        if marker is None:
            raise ValueError("This task requires a marker")
        fields = {"name": obj.name, "extras": sorted(obj.extras), "specifier": str(obj.specifier), "url": obj.url} if kind == "requirement" else None
        return {"literals": literals(marker._markers, value_type),
                "evaluation": marker.evaluate(environment=dict(env)), "requirement": fields}

    try:
        original = constructor(case["input"])
        result["before"] = snapshot(original)
    except Exception as exc:
        result["initial_error"] = type(exc).__name__
        return result
    try:
        result["serialized"] = original.serialize() if kind == "value" else str(original)
    except Exception as exc:
        result["serialization_error"] = type(exc).__name__
        return result
    if kind != "value":
        try:
            result["after"] = snapshot(constructor(result["serialized"]))
        except Exception as exc:
            result["roundtrip_error"] = type(exc).__name__
    return result


def run(repo, manifest, oracle):
    validate(manifest, oracle)
    repo = repo.resolve()
    scope = capture_scope(repo)
    if any(n == "packaging" or n.startswith("packaging.") for n in sys.modules):
        raise ValueError("Use a fresh process")
    sys.path.insert(0, str(repo / "src"))
    from packaging.markers import Marker
    from packaging.requirements import Requirement
    from packaging._parser import Value
    rows = []
    for case in manifest["cases"]:
        env = dict(manifest["environment"], **case["overrides"])
        observed = observe(case, env, Marker, Requirement, Value)
        expected = oracle["expected"][case["id"]]
        actual = {k: observed[k] for k in expected}
        rows.append({"id": case["id"], "kind": case["kind"], "environment": env,
                     "observed": observed, "status": "PASS" if actual == expected else "FAIL"})
    origins = {}
    for name, module in list(sys.modules.items()):
        if name == "packaging" or name.startswith("packaging."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(repo / "src/packaging"):
                raise ValueError("Import escapes reviewed package")
            origins[name] = path.relative_to(repo).as_posix()
    if capture_scope(repo) != scope:
        raise ValueError("Reviewed code changed during execution")
    return {"code_scope": scope, "module_origins": origins, "tests": rows,
            "runtime": {"python": platform.python_version(), "platform": sys.platform},
            "explicit_environment_only_in_receipts": True, "network_or_installation_performed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "manifest", "oracle"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--oracle-sha256", required=True)
    args = parser.parse_args(argv)
    report = run(args.repo, read_pinned(args.manifest, args.manifest_sha256), read_pinned(args.oracle, args.oracle_sha256))
    report.update(manifest_sha256=args.manifest_sha256, oracle_sha256=args.oracle_sha256,
                  probe_sha256=digest(Path(__file__).read_bytes()))
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if all(t["status"] == "PASS" for t in report["tests"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
