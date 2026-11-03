"""Observe pinned JSON payloads on a prepared, pure-Python simplejson snapshot."""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import re
import sys

SCOPE = tuple("simplejson/" + name for name in (
    "__init__.py", "compat.py", "decoder.py", "encoder.py", "ordered_dict.py",
    "scanner.py", "tests/__init__.py", "tests/test_unicode.py"))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read_pinned(path, expected):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected an ordinary pinned file")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536 or digest(raw) != expected:
        raise ValueError("Pinned input differs or is oversized")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def validate(manifest, oracle):
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "cases"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1):
        raise ValueError("Invalid manifest")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 16:
        raise ValueError("Invalid case count")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "file", "api", "representation"}:
            raise ValueError("Invalid case fields")
        if (not isinstance(case["id"], str) or not re.fullmatch(r"[a-z_]{1,40}", case["id"])
                or case["id"] in seen):
            raise ValueError("Invalid or duplicate case ID")
        seen.add(case["id"])
        if not isinstance(case["file"], str) or not re.fullmatch(r"[a-z-]{1,40}\.bin", case["file"]):
            raise ValueError("Invalid direct payload name")
        if case["api"] not in ("load", "loads") or case["representation"] not in ("text", "bytes"):
            raise ValueError("Invalid parser route")
    if (not isinstance(oracle, dict) or set(oracle) != {"schema_version", "expected"}
            or type(oracle["schema_version"]) is not int or oracle["schema_version"] != 1
            or not isinstance(oracle["expected"], dict) or set(oracle["expected"]) != seen):
        raise ValueError("Oracle must cover the exact cases")
    for value in oracle["expected"].values():
        if not isinstance(value, dict) or set(value) != {"value", "error_kind"}:
            raise ValueError("Invalid expected output")
        if value["error_kind"] not in (None, "JSONDecodeError"):
            raise ValueError("Invalid expected error")
        if value["error_kind"] is not None and value["value"] is not None:
            raise ValueError("Error output cannot carry a value")
        canonical(value)


def observe(module, case, inputs):
    path = inputs / case["file"]
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected an ordinary payload file")
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("Oversized payload")
    identity = {"path": case["file"], "bytes": len(raw), "sha256": digest(raw)}
    # Decode UTF-8, not utf-8-sig: the requested BOM must reach the target.
    payload = raw.decode("utf-8") if case["representation"] == "text" else raw
    if case["api"] == "load":
        payload = io.StringIO(payload) if isinstance(payload, str) else io.BytesIO(payload)
    try:
        value = getattr(module, case["api"])(payload)
        return {"value": value, "error_kind": None}, identity, None
    except Exception as error:
        return {"value": None, "error_kind": type(error).__name__}, identity, str(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "inputs", "manifest", "oracle"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("manifest-sha256", "oracle-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    manifest = read_pinned(args.manifest, args.manifest_sha256)
    oracle = read_pinned(args.oracle, args.oracle_sha256)
    validate(manifest, oracle)
    source = args.repo.resolve()
    scope = {name: digest((source / name).read_bytes()) for name in SCOPE}
    if any(name == "simplejson" or name.startswith("simplejson.") for name in sys.modules):
        raise ValueError("Run in a fresh interpreter")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    module = importlib.import_module("simplejson")
    if (module._import_c_make_encoder() is not None
            or module.decoder.scanstring is not module.decoder.py_scanstring
            or module.scanner.make_scanner is not module.scanner.py_make_scanner):
        raise ValueError("Expected pure-Python target")
    rows = []
    for case in manifest["cases"]:
        actual, identity, error = observe(module, case, args.inputs)
        rows.append({"id": case["id"], "actual": actual, "input": identity, "error": error,
                     "status": "PASS" if canonical(actual) == canonical(oracle["expected"][case["id"]]) else "FAIL"})
    imported = {}
    for name, loaded in tuple(sys.modules.items()):
        if name == "simplejson" or name.startswith("simplejson."):
            relative = Path(loaded.__file__).resolve().relative_to(source).as_posix()
            if relative not in scope:
                raise ValueError("Unpinned target module")
            imported[name] = relative
    if scope != {name: digest((source / name).read_bytes()) for name in SCOPE}:
        raise ValueError("Source changed during observation")
    result = {"schema_version": 1, "code_scope": scope, "imported_target_modules": imported,
              "pure_python": True, "probe_sha256": digest(Path(__file__).read_bytes()),
              "manifest_sha256": args.manifest_sha256, "oracle_sha256": args.oracle_sha256,
              "runtime": {"implementation": sys.implementation.name, "version": list(sys.version_info[:3])},
              "tests": rows, "actual_outputs": {row["id"]: row["actual"] for row in rows},
              "actual_inputs": {row["id"]: row["input"] for row in rows}}
    print(canonical(result))
    return int(any(row["status"] != "PASS" for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
