"""Observe ConfigArgParse on pinned cases; input identity is separate from output success."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read_pinned(path, expected):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected an ordinary pinned file")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536 or digest(raw) != expected:
        raise ValueError("Pinned input differs or is oversized")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs)

def validate(manifest, oracle):
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "cases"} or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Invalid manifest")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 16:
        raise ValueError("Invalid case count")
    seen = set()
    allowed_args = {"--feature", "--no-feature", "--mega", "--giga", "-m", "-g"}
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "kind", "args", "env", "config"}:
            raise ValueError("Unknown case fields")
        if not isinstance(case["id"], str) or not re.fullmatch(r"[a-z_]{1,40}", case["id"]) or case["id"] in seen:
            raise ValueError("Invalid or duplicate case ID")
        seen.add(case["id"])
        if case["kind"] not in ("bool", "mode") or not isinstance(case["config"], str) or not re.fullmatch(r"[a-z-]{1,40}\.ini", case["config"]):
            raise ValueError("Invalid parser kind or direct config name")
        if not isinstance(case["args"], list) or len(case["args"]) > 2 or any(not isinstance(a, str) or a not in allowed_args for a in case["args"]):
            raise ValueError("Invalid arguments")
        if not isinstance(case["env"], dict) or not set(case["env"]).issubset({"MEGA", "GIGA"}) or any(v != "true" for v in case["env"].values()):
            raise ValueError("Invalid explicit environment")
    if not isinstance(oracle, dict) or set(oracle) != {"schema_version", "expected"} or type(oracle["schema_version"]) is not int or oracle["schema_version"] != 1 or not isinstance(oracle["expected"], dict) or set(oracle["expected"]) != seen:
        raise ValueError("Oracle does not cover the exact cases")
    for value in oracle["expected"].values():
        if not isinstance(value, dict) or set(value) != {"exit_code", "value", "error_kind"}:
            raise ValueError("Invalid expected output fields")
        if type(value["exit_code"]) is not int or value["exit_code"] not in (0, 2):
            raise ValueError("Invalid exit code")
        if value["exit_code"] == 2:
            if value["value"] is not None or value["error_kind"] != "mutually_exclusive_conflict":
                raise ValueError("Invalid conflict output")
        elif value["error_kind"] is not None or not (type(value["value"]) is bool or value["value"] in ("mega", "giga")):
            raise ValueError("Invalid successful output")

def observe(module, case, inputs):
    path = inputs / case["config"]
    reads = []
    def opener(filename):
        actual = Path(filename)
        if actual.resolve() != path.resolve() or not actual.is_file() or actual.is_symlink():
            raise ValueError("Unexpected or indirect config read")
        with actual.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError("Config file too large")
        reads.append({"path": case["config"], "bytes": len(raw), "sha256": digest(raw)})
        stream = io.StringIO(raw.decode("utf-8")); stream.name = case["config"]
        return stream
    parser = module.ArgumentParser(prog="input-provenance", default_config_files=[str(path)], config_file_open_func=opener, args_for_setting_config_path=[])
    if case["kind"] == "bool":
        group = parser.add_argument_group("features").add_mutually_exclusive_group()
        group.add_argument("--feature", dest="feature", action="store_true")
        group.add_argument("--no-feature", dest="feature", action="store_false")
    else:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("-m", "--mega", dest="mode", action="store_const", const="mega", env_var="MEGA")
        group.add_argument("-g", "--giga", dest="mode", action="store_const", const="giga", env_var="GIGA")
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            ns = parser.parse_args(case["args"], env_vars=case["env"])
            observed = {"exit_code": 0, "value": getattr(ns, "feature" if case["kind"] == "bool" else "mode"), "error_kind": None}
        except SystemExit as error:
            observed = {"exit_code": error.code, "value": None, "error_kind": "mutually_exclusive_conflict" if "not allowed with argument" in stderr.getvalue() else "other"}
    if len(reads) != 1:
        raise ValueError("Expected exactly one actual config read")
    return observed, reads[0], stderr.getvalue()

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
    scope = {n: digest((args.repo / n).read_bytes()) for n in ("configargparse.py", "tests/__init__.py", "tests/test_configargparse.py")}
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("observed_configargparse", args.repo / "configargparse.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rows = []
    for case in manifest["cases"]:
        observed, actual_input, stderr = observe(module, case, args.inputs)
        rows.append({"id": case["id"], "actual": observed, "input": actual_input, "stderr": stderr, "status": "PASS" if observed == oracle["expected"][case["id"]] else "FAIL"})
    assert scope == {n: digest((args.repo / n).read_bytes()) for n in scope}
    result = {"schema_version": 1, "code_scope": scope, "probe_sha256": digest(Path(__file__).read_bytes()),
              "manifest_sha256": args.manifest_sha256, "oracle_sha256": args.oracle_sha256,
              "runtime": {"implementation": sys.implementation.name, "version": list(sys.version_info[:3])},
              "tests": rows, "actual_outputs": {r["id"]: r["actual"] for r in rows},
              "actual_inputs": {r["id"]: r["input"] for r in rows}}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return int(any(r["status"] != "PASS" for r in rows))

if __name__ == "__main__":
    raise SystemExit(main())
