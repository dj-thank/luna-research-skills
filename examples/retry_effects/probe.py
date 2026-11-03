"""Compare sequential retry policies using real TinyDB JSONStorage writes.

Trusted source-only execution, synthetic inputs, fresh retained scratch files.
Faults are local injections, not network, process-crash or concurrency tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

sys.dont_write_bytecode = True
FILES = ["__init__.py", "database.py", "middlewares.py", "mypy_plugin.py",
         "operations.py", "queries.py", "storages.py", "table.py", "utils.py", "version.py"]
POLICIES = ("plain_insert", "request_key", "payload_key")
CANARY = {"1": {"sentinel": "X37 keep unrelated data"}}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, pin):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != pin:
        raise ValueError("Input size or independently supplied pin differs")
    return json.loads(raw)


def validate(manifest, oracle):
    if set(manifest) != {"schema_version", "policy", "cases"} or manifest["schema_version"] != 1:
        raise ValueError("Unknown manifest schema")
    if manifest["policy"] not in POLICIES:
        raise ValueError("Unknown retry policy")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise ValueError("Expected bounded case list")
    seen = set()
    for case in cases:
        if set(case) != {"id", "initial", "operations"}:
            raise ValueError("Unknown case field")
        if not isinstance(case["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", case["id"]) or case["id"] in seen:
            raise ValueError("Unsafe or duplicate case ID")
        seen.add(case["id"])
        if not isinstance(case["initial"], list) or len(case["initial"]) > 4:
            raise ValueError("Too many initial documents")
        if not isinstance(case["operations"], list) or not 1 <= len(case["operations"]) <= 4:
            raise ValueError("Expected bounded operations")
        for row in case["initial"] + case["operations"]:
            fields = {"request_id", "payload", "fault"} if "fault" in row else {"request_id", "payload"}
            if set(row) != fields or any(not isinstance(row[k], str) or len(row[k]) > 1024 for k in ("request_id", "payload")):
                raise ValueError("Invalid request")
            if not re.fullmatch(r"X37_[A-Z]+", row["request_id"]):
                raise ValueError("Use synthetic request IDs")
        if any(set(row) != {"request_id", "payload"} for row in case["initial"]):
            raise ValueError("Initial documents cannot inject faults")
        if len({row["request_id"] for row in case["initial"]}) != len(case["initial"]):
            raise ValueError("Initial request identities must be unique")
        if any(row.get("fault") not in ("none", "before_commit", "after_commit") for row in case["operations"]):
            raise ValueError("Unknown or missing fault point")
    if set(oracle) != {"schema_version", "expected"} or oracle["schema_version"] != 1 or set(oracle["expected"]) != seen:
        raise ValueError("Oracle and manifest cases differ")
    for row in oracle["expected"].values():
        if set(row) != {"responses", "documents", "execution_writes", "attempts"}:
            raise ValueError("Unknown oracle field")
        if not isinstance(row["responses"], list) or any(s not in ("accepted", "conflict") for s in row["responses"]):
            raise ValueError("Invalid expected responses")
        if not isinstance(row["documents"], list) or any(set(d) != {"request_id", "payload"} for d in row["documents"]):
            raise ValueError("Invalid expected documents")
        if type(row["execution_writes"]) is not int or type(row["attempts"]) is not int:
            raise ValueError("Expected integer bounds")
        if not 0 <= row["execution_writes"] <= 8 or not 1 <= row["attempts"] <= 8:
            raise ValueError("Expected bounded counts")


def capture_scope(repo):
    folder = repo / "tinydb"
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.py"))
    if names != sorted(FILES) or any(folder.rglob("*.pyc")) or any(folder.rglob("*.pyo")):
        raise ValueError("Unexpected source inventory or bytecode cache")
    scope = {}
    for name in names:
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError("Source escapes checkout")
        scope["tinydb/" + name] = digest(path.read_bytes())
    return scope


class InjectedFailure(Exception):
    pass


def perform(db_type, storage, query, path, request, policy):
    """One application invocation, with common conflict rejection in all arms."""
    with db_type(path, storage=storage, encoding="utf-8", ensure_ascii=False) as db:
        existing = db.get(query().request_id == request["request_id"])
        if existing is not None and existing["payload"] != request["payload"]:
            return "conflict"
        if policy == "request_key" and existing is not None:
            return "accepted"
        if policy == "payload_key" and db.get(query().payload == request["payload"]) is not None:
            return "accepted"
        db.insert({"request_id": request["request_id"], "payload": request["payload"]})
    return "accepted"


def run_case(db_type, storage_type, query, case, policy, expected, scratch):
    folder = scratch / case["id"]
    folder.mkdir()
    path = folder / "synthetic.json"
    writes = []

    class CountingStorage(storage_type):
        def write(self, data):
            super().write(data)
            writes.append("completed_write")

    with db_type(path, storage=CountingStorage, encoding="utf-8", ensure_ascii=False) as db:
        db.table("canary").insert(CANARY["1"])
        if case["initial"]:
            db.insert_multiple(case["initial"])
    initial = json.loads(path.read_bytes())
    setup_writes = len(writes)
    trace, responses = [], []
    for operation, request in enumerate(case["operations"]):
        for attempt in (1, 2):
            fault = request["fault"] if attempt == 1 else "none"
            result, error = None, None
            try:
                if fault == "before_commit":
                    raise InjectedFailure()
                result = perform(db_type, CountingStorage, query, path, request, policy)
                if fault == "after_commit":
                    result = None
                    raise InjectedFailure()
            except InjectedFailure:
                error = fault
            state = json.loads(path.read_bytes())
            trace.append({"operation": operation, "attempt": attempt,
                          "request_id": request["request_id"], "response": result,
                          "injected_error": error, "state_after": state})
            if error is None:
                responses.append(result)
                break
        else:
            raise ValueError("Retry budget exhausted")
    # Reopen storage after all invocations, independently of their return values.
    with db_type(path, encoding="utf-8") as db:
        documents = [dict(doc) for doc in db.all()]
    final = json.loads(path.read_bytes())
    desired = {"canary": CANARY,
               "_default": {str(i + 1): doc for i, doc in enumerate(expected["documents"])}}
    outcome_ok = responses == expected["responses"] and len(trace) == expected["attempts"]
    effect_ok = final == desired and documents == expected["documents"] and len(writes) - setup_writes == expected["execution_writes"]
    if initial["canary"] != CANARY or any(t["state_after"].get("canary") != CANARY for t in trace):
        raise ValueError("Unrelated table changed")
    return {"id": case["id"], "responses": responses, "attempt_trace": trace,
            "initial_state": initial, "final_state": final, "documents": documents,
            "setup_writes": setup_writes, "execution_writes": len(writes) - setup_writes,
            "final_file_sha256": digest(path.read_bytes()),
            "outcome_status": "PASS" if outcome_ok else "FAIL",
            "effect_status": "PASS" if effect_ok else "FAIL",
            "status": "PASS" if outcome_ok and effect_ok else "FAIL"}


def run(repo, manifest, oracle, scratch):
    validate(manifest, oracle)
    repo = repo.resolve()
    scope = capture_scope(repo)
    if any(n == "tinydb" or n.startswith("tinydb.") for n in sys.modules):
        raise ValueError("Use a fresh process")
    if scratch.exists() or scratch.is_symlink() or not scratch.parent.is_dir():
        raise ValueError("Scratch must be new, with an existing parent")
    scratch.mkdir()
    canary = scratch / "canary.txt"
    canary.write_bytes(b"X37 unrelated synthetic file\n")
    sys.path.insert(0, str(repo))
    from tinydb import TinyDB, JSONStorage, Query
    rows = [run_case(TinyDB, JSONStorage, Query, c, manifest["policy"],
                     oracle["expected"][c["id"]], scratch) for c in manifest["cases"]]
    origins = {}
    for name, module in list(sys.modules.items()):
        if name == "tinydb" or name.startswith("tinydb."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(repo / "tinydb"):
                raise ValueError("Import escapes reviewed package")
            origins[name] = path.relative_to(repo).as_posix()
    if capture_scope(repo) != scope or canary.read_bytes() != b"X37 unrelated synthetic file\n":
        raise ValueError("Code or unrelated synthetic file changed")
    return {"code_scope": scope, "module_origins": origins, "tests": rows,
            "policy": manifest["policy"], "scratch_retained": True,
            "runtime": {"python": platform.python_version(), "platform": sys.platform},
            "single_writer": True, "network_or_process_crash_tested": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "manifest", "oracle", "scratch"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--oracle-sha256", required=True)
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
