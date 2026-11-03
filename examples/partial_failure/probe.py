"""Run trusted upstream/call-site pairs against independently pinned partial-failure answers."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import re
import sys

sys.dont_write_bytecode = True
FILES = ["__init__.py", "more.py", "recipes.py", "tests/__init__.py", "tests/test_more.py", "tests/test_recipes.py"]
STATE_KEYS = {"outputs", "written", "source_seen", "source_finalized", "resource_closed", "exit_count", "exit_errors"}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read_pinned(path, pin):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != pin:
        raise ValueError("Input size or independently supplied pin differs")
    return json.loads(raw)

def strings(value):
    return isinstance(value, list) and len(value) <= 8 and all(isinstance(v, str) and len(v) <= 64 for v in value)

def validate(manifest, oracle):
    for value, key in ((manifest, "cases"), (oracle, "expected")):
        if not isinstance(value, dict) or set(value) != {"schema_version", key} or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unknown input schema")
    if not isinstance(manifest["cases"], list) or not 1 <= len(manifest["cases"]) <= 24 or not isinstance(oracle["expected"], dict):
        raise ValueError("Expected bounded cases and answers")
    seen = set()
    for case in manifest["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "items", "fault", "at"}:
            raise ValueError("Unknown case fields")
        key = case["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) or key in seen:
            raise ValueError("Unsafe or duplicate case ID")
        seen.add(key)
        if not strings(case["items"]) or case["fault"] not in ("none", "source", "consumer") or type(case["at"]) is not int:
            raise ValueError("Invalid case")
        if case["fault"] == "none" and case["at"] != 0:
            raise ValueError("Normal case has a fault offset")
        if case["fault"] == "source" and not 0 <= case["at"] <= len(case["items"]):
            raise ValueError("Source offset outside input")
        if case["fault"] == "consumer" and not 0 <= case["at"] < len(case["items"]):
            raise ValueError("Consumer offset outside input")
        answer = oracle["expected"].get(key)
        if not isinstance(answer, dict) or set(answer) != {"terminal", "state"}:
            raise ValueError("Missing complete answer")
        terminal, state = answer["terminal"], answer["state"]
        if terminal is not None and (not isinstance(terminal, dict) or set(terminal) != {"type", "message"} or terminal["type"] != "InjectedError" or not isinstance(terminal["message"], str) or len(terminal["message"]) > 64):
            raise ValueError("Invalid terminal answer")
        if not isinstance(state, dict) or set(state) != STATE_KEYS:
            raise ValueError("Missing partial-state answer")
        if not strings(state["outputs"]) or not strings(state["source_seen"]) or not isinstance(state["written"], str) or len(state["written"]) > 1024:
            raise ValueError("Invalid bounded state")
        if any(type(state[k]) is not bool for k in ("source_finalized", "resource_closed")) or type(state["exit_count"]) is not int or not 0 <= state["exit_count"] <= 1:
            raise ValueError("Invalid cleanup state")
        if not isinstance(state["exit_errors"], list) or len(state["exit_errors"]) != state["exit_count"] or any(v not in (None, "InjectedError") for v in state["exit_errors"]):
            raise ValueError("Invalid exit events")
    if seen != set(oracle["expected"]):
        raise ValueError("Oracle and manifest differ")

def capture_scope(repo):
    folder = repo / "more_itertools"
    paths = sorted(folder.rglob("*.py"))
    if sorted(p.relative_to(folder).as_posix() for p in paths) != sorted(FILES) or any(folder.rglob("*.pyc")) or any(folder.rglob("*.pyo")):
        raise ValueError("Unexpected package inventory or bytecode cache")
    if folder.is_symlink():
        raise ValueError("Package symlink")
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError("Source escapes package")
    return {p.relative_to(repo).as_posix(): digest(p.read_bytes()) for p in paths}

class InjectedError(Exception):
    pass

def observe(case, operation):
    outputs, source_seen, exits, retained = [], [], [], []
    finalized = False
    written = []
    class Resource:
        def __init__(self):
            self.stream = io.StringIO()
        def __enter__(self):
            return self
        def __exit__(self, kind, value, tb):
            exits.append(kind.__name__ if kind else None)
            self.stream.close()
        def write(self, item):
            self.stream.write(item + "\n")
            written.append(item + "\n")
    resource = Resource()
    def source():
        nonlocal finalized
        try:
            for index, item in enumerate(case["items"]):
                if case["fault"] == "source" and index == case["at"]:
                    raise InjectedError("source:" + str(index))
                source_seen.append(item)
                yield item
            if case["fault"] == "source" and case["at"] == len(case["items"]):
                raise InjectedError("source:" + str(case["at"]))
        finally:
            finalized = True
    iterator = source()
    def consume(handle, item):
        if case["fault"] == "consumer" and len(outputs) == case["at"]:
            raise InjectedError("consumer:" + str(case["at"]))
        handle.write(item)
        outputs.append(item)
    terminal = None
    try:
        operation(resource, iterator, consume, retained)
    except InjectedError as error:
        terminal = {"type": type(error).__name__, "message": str(error)}
    state = {"outputs": outputs.copy(), "written": "".join(written), "source_seen": source_seen.copy(),
             "source_finalized": finalized, "resource_closed": resource.stream.closed,
             "exit_count": len(exits), "exit_errors": exits.copy()}
    # Snapshot precedes harness teardown; no reliance on garbage-collection timing.
    for managed in retained:
        managed.close()
    iterator.close()
    resource.stream.close()
    return terminal, state

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--variant", required=True, choices=("base", "fixed", "swallow"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--oracle-sha256", required=True)
    args = parser.parse_args()
    manifest = read_pinned(args.manifest, args.manifest_sha256)
    oracle = read_pinned(args.oracle, args.oracle_sha256)
    validate(manifest, oracle)
    repo = args.repo.resolve()
    scope = capture_scope(repo)
    sys.path.insert(0, str(repo))
    import more_itertools
    import six
    for name, module in list(sys.modules.items()):
        if name == "more_itertools" or name.startswith("more_itertools."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(repo):
                raise ValueError("Imported upstream package outside reviewed root")
    if hasattr(more_itertools, "context") != (args.variant == "base"):
        raise ValueError("Wrong historical API version for this call site")
    callsite = Path(__file__).with_name(args.variant + ".py")
    spec = importlib.util.spec_from_file_location("reviewed_callsite", callsite)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tests = []
    for case in manifest["cases"]:
        terminal, state = observe(case, module.run)
        expected = oracle["expected"][case["id"]]
        terminal_status = "PASS" if terminal == expected["terminal"] else "FAIL"
        state_status = "PASS" if state == expected["state"] else "FAIL"
        tests.append({"id": case["id"], "terminal": terminal, "state": state,
                      "terminal_status": terminal_status, "state_status": state_status,
                      "status": "PASS" if terminal_status == state_status == "PASS" else "FAIL"})
    assert capture_scope(repo) == scope
    report = {"schema_version": 1, "code_scope": scope, "callsite_sha256": digest(callsite.read_bytes()),
              "dependency": {"six_version": six.__version__, "six_sha256": digest(Path(six.__file__).read_bytes())},
              "probe_sha256": digest(Path(__file__).read_bytes()), "manifest_sha256": args.manifest_sha256,
              "oracle_sha256": args.oracle_sha256, "runtime": {"python": platform.python_version(), "platform": sys.platform},
              "tests": tests}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return int(any(row["status"] != "PASS" for row in tests))

if __name__ == "__main__":
    raise SystemExit(main())
