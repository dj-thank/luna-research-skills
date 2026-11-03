"""Capture raw bytes and the exact final str passed to a pinned TOML parser."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

SCOPE = ("toml.py", "tests/decoding_test.py")


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
        if not isinstance(case, dict) or set(case) != {"id", "file", "preprocess", "control_text"}:
            raise ValueError("Invalid case fields")
        if (not isinstance(case["id"], str) or not re.fullmatch(r"[a-z_]{1,40}", case["id"])
                or case["id"] in seen):
            raise ValueError("Invalid or duplicate case ID")
        seen.add(case["id"])
        if not isinstance(case["file"], str) or not re.fullmatch(r"[a-z-]{1,40}\.bin", case["file"]):
            raise ValueError("Invalid direct payload name")
        if case["preprocess"] not in ("utf8", "utf8_crlf_to_lf"):
            raise ValueError("Invalid declared preprocessing")
        control = case["control_text"]
        if control is not None and (not isinstance(control, str) or len(control.encode("utf-8")) > 4096):
            raise ValueError("Invalid explicit control text")
    if (not isinstance(oracle, dict) or set(oracle) != {"schema_version", "expected"}
            or type(oracle["schema_version"]) is not int or oracle["schema_version"] != 1
            or not isinstance(oracle["expected"], dict) or set(oracle["expected"]) != seen):
        raise ValueError("Oracle must cover the exact cases")
    for value in oracle["expected"].values():
        if not isinstance(value, dict) or set(value) != {"value", "error_kind"}:
            raise ValueError("Invalid expected output")
        if value["error_kind"] not in (None, "TomlDecodeError"):
            raise ValueError("Invalid expected error")
        if value["error_kind"] is not None and value["value"] is not None:
            raise ValueError("Error output cannot carry a value")
        canonical(value)


def parser_identity(text):
    raw = text.encode("utf-8")
    return {"type": "str", "characters": len(text), "utf8_bytes": len(raw),
            "sha256": digest(raw), "text": text}


def observe(module, case, inputs, mode):
    if mode not in ("declared", "rewrite_quotes"):
        raise ValueError("Invalid control mode")
    path = inputs / case["file"]
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected an ordinary payload file")
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("Oversized payload")
    identity = {"path": case["file"], "bytes": len(raw), "sha256": digest(raw)}
    payload = raw.decode("utf-8")
    if case["preprocess"] == "utf8_crlf_to_lf":
        payload = payload.replace("\r\n", "\n")
    if mode == "rewrite_quotes" and case["control_text"] is not None:
        payload = case["control_text"]
    # This immutable object is captured AFTER every transformation and is the
    # same object passed to loads. Never reconstruct this receipt from raw files.
    parser_input = parser_identity(payload)
    try:
        value = module.loads(payload)
        actual, error = {"value": value, "error_kind": None}, None
    except Exception as caught:
        actual = {"value": None, "error_kind": type(caught).__name__}
        error = str(caught)
    return actual, identity, parser_input, error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "inputs", "manifest", "oracle"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("manifest-sha256", "oracle-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--mode", choices=("declared", "rewrite_quotes"), default="declared")
    args = parser.parse_args()
    manifest = read_pinned(args.manifest, args.manifest_sha256)
    oracle = read_pinned(args.oracle, args.oracle_sha256)
    validate(manifest, oracle)
    source = args.repo.resolve()
    scope = {name: digest((source / name).read_bytes()) for name in SCOPE}
    if "toml" in sys.modules:
        raise ValueError("Run in a fresh interpreter")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("toml", source / "toml.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["toml"] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != source / "toml.py":
        raise ValueError("Unpinned target module")
    rows = []
    for case in manifest["cases"]:
        actual, identity, parser_input, error = observe(module, case, args.inputs, args.mode)
        rows.append({"id": case["id"], "actual": actual, "input": identity,
                     "parser_input": parser_input, "error": error,
                     "status": "PASS" if canonical(actual) == canonical(oracle["expected"][case["id"]]) else "FAIL"})
    if scope != {name: digest((source / name).read_bytes()) for name in SCOPE}:
        raise ValueError("Source changed during observation")
    result = {"schema_version": 1, "code_scope": scope, "imported_target_modules": {"toml": "toml.py"},
              "mode": args.mode, "probe_sha256": digest(Path(__file__).read_bytes()),
              "manifest_sha256": args.manifest_sha256, "oracle_sha256": args.oracle_sha256,
              "runtime": {"implementation": sys.implementation.name, "version": list(sys.version_info[:3])},
              "tests": rows, "actual_outputs": {row["id"]: row["actual"] for row in rows},
              "actual_inputs": {row["id"]: row["input"] for row in rows},
              "actual_parser_inputs": {row["id"]: row["parser_input"] for row in rows}}
    print(canonical(result))
    return int(any(row["status"] != "PASS" for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
