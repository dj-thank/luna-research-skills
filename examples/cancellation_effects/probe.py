"""Execute bounded cancellation policies on an unchanged schedule checkout.

Trusted source-only execution; sequential callbacks and synthetic retained files.
No threads, process crashes, deadline timing or distributed guarantees are tested.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

sys.dont_write_bytecode = True
POLICIES = ("unschedule_only", "generation_guard", "name_tombstone")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, pin):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != pin:
        raise ValueError("Input size or independently supplied pin differs")
    return json.loads(raw)


def validate(manifest, oracle):
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "policy", "cases"} or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unknown manifest schema")
    if manifest["policy"] not in POLICIES:
        raise ValueError("Unknown cancellation policy")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise ValueError("Expected bounded case list")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "initial", "during", "after"}:
            raise ValueError("Unknown case fields")
        key = case["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) or key in seen:
            raise ValueError("Unsafe or duplicate case ID")
        seen.add(key)
        latest, submitted = {}, set()
        for stage in ("initial", "during", "after"):
            if not isinstance(case[stage], list) or len(case[stage]) > 4:
                raise ValueError("Expected bounded commands")
            for op in case[stage]:
                if not isinstance(op, dict) or op.get("op") not in ("submit", "cancel"):
                    raise ValueError("Unknown command")
                fields = {"op", "request_id", "generation"} | ({"payload"} if op["op"] == "submit" else set())
                if set(op) != fields or not isinstance(op["request_id"], str) or not re.fullmatch(r"X38_[A-Z]+", op["request_id"]):
                    raise ValueError("Use synthetic request IDs")
                if type(op["generation"]) is not int or not 1 <= op["generation"] <= 8:
                    raise ValueError("Expected bounded integer generation")
                token = (op["request_id"], op["generation"])
                if op["op"] == "submit":
                    if not isinstance(op["payload"], str) or len(op["payload"]) > 1024 or op["generation"] <= latest.get(op["request_id"], 0):
                        raise ValueError("Invalid payload or reused generation")
                    latest[op["request_id"]] = op["generation"]
                    submitted.add(token)
                elif token not in submitted:
                    raise ValueError("Cancellation must name a previously submitted generation")
    if not isinstance(oracle, dict) or set(oracle) != {"schema_version", "expected"} or type(oracle["schema_version"]) is not int or oracle["schema_version"] != 1 or not isinstance(oracle["expected"], dict) or set(oracle["expected"]) != seen:
        raise ValueError("Oracle and manifest cases differ")
    for row in oracle["expected"].values():
        if not isinstance(row, dict) or set(row) != {"acknowledgments", "effects", "callbacks", "writes"}:
            raise ValueError("Unknown oracle fields")
        if not isinstance(row["acknowledgments"], list) or len(row["acknowledgments"]) > 12 or any(not isinstance(s, str) for s in row["acknowledgments"]):
            raise ValueError("Invalid expected acknowledgments")
        if not isinstance(row["effects"], list) or len(row["effects"]) > 12 or any(not isinstance(e, dict) or set(e) != {"request_id", "generation", "payload"} for e in row["effects"]):
            raise ValueError("Invalid expected effects")
        if any(type(row[k]) is not int or not 0 <= row[k] <= 12 for k in ("callbacks", "writes")):
            raise ValueError("Expected bounded integer counts")


def capture_scope(repo):
    folder = repo / "schedule"
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.py"))
    if names != ["__init__.py"] or any(folder.rglob("*.pyc")) or any(folder.rglob("*.pyo")):
        raise ValueError("Unexpected source inventory or bytecode cache")
    path = folder / "__init__.py"
    if path.is_symlink() or not path.resolve().is_relative_to(repo):
        raise ValueError("Source escapes checkout")
    return {"schedule/__init__.py": digest(path.read_bytes())}


def run_case(module, case, policy, expected, scratch):
    folder = scratch / case["id"]
    folder.mkdir()
    path = folder / "effects.jsonl"
    path.write_bytes(b"")
    scheduler = module.Scheduler()
    current, handles, cancelled_names = {}, {}, set()
    acknowledgments, trace, drains = [], [], []
    callbacks = writes = 0
    stage = "initial"

    def command(op):
        key, generation = op["request_id"], op["generation"]
        token = (key, generation)
        if op["op"] == "submit":
            current[key] = {"generation": generation, "active": True}

            def work():
                nonlocal callbacks, writes
                callbacks += 1
                valid = current.get(key) == {"generation": generation, "active": True}
                allowed = policy == "unschedule_only" or (policy == "generation_guard" and valid) or (policy == "name_tombstone" and key not in cancelled_names)
                trace.append({"event": "callback", "stage": stage, "request_id": key,
                              "generation": generation, "still_scheduled": handles[token] in scheduler.jobs,
                              "current_valid": valid, "decision": "write" if allowed else "discard"})
                if allowed:
                    effect = {"request_id": key, "generation": generation, "payload": op["payload"]}
                    with path.open("ab") as fp:
                        fp.write((json.dumps(effect, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
                    writes += 1
                if current.get(key, {}).get("generation") == generation:
                    current[key]["active"] = False
                return module.CancelJob

            handles[token] = scheduler.every().second.do(work)
            result = "registered"
        else:
            result = scheduler.cancel_job(handles[token])
            if result is not None:
                raise ValueError("Unexpected cancellation API result")
            if current.get(key, {}).get("generation") == generation:
                current[key]["active"] = False
            cancelled_names.add(key)
            result = "cancelled"
        acknowledgment = f"{result}:{key}:{generation}"
        acknowledgments.append(acknowledgment)
        trace.append({"event": "command", "stage": stage, "acknowledgment": acknowledgment})

    def control():
        trace.append({"event": "controller", "stage": stage})
        for op in case["during"]:
            command(op)
        return module.CancelJob

    # The controller is first in the real scheduler's run_all snapshot.
    scheduler.every().second.do(control)
    for op in case["initial"]:
        command(op)
    stage = "first_drain"
    drains.append(scheduler.run_all(delay_seconds=0))
    first_effects = [json.loads(line) for line in path.read_bytes().splitlines()]
    stage = "after"
    for op in case["after"]:
        command(op)
    stage = "second_drain"
    drains.append(scheduler.run_all(delay_seconds=0))
    effects = [json.loads(line) for line in path.read_bytes().splitlines()]
    outcome_ok = acknowledgments == expected["acknowledgments"] and callbacks == expected["callbacks"] and not scheduler.jobs and drains == [None, None]
    effect_ok = effects == expected["effects"] and writes == expected["writes"]
    return {"id": case["id"], "acknowledgments": acknowledgments, "trace": trace,
            "first_drain_effects": first_effects, "effects": effects, "callback_count": callbacks,
            "controller_calls": sum(t["event"] == "controller" for t in trace),
            "write_count": writes, "pending_jobs": len(scheduler.jobs), "drain_returns": drains,
            "final_file_sha256": digest(path.read_bytes()),
            "outcome_status": "PASS" if outcome_ok else "FAIL",
            "effect_status": "PASS" if effect_ok else "FAIL",
            "status": "PASS" if outcome_ok and effect_ok else "FAIL"}


def run(repo, manifest, oracle, scratch):
    validate(manifest, oracle)
    repo = repo.resolve()
    scope = capture_scope(repo)
    if any(n == "schedule" or n.startswith("schedule.") for n in sys.modules):
        raise ValueError("Use a fresh process")
    if scratch.exists() or scratch.is_symlink() or not scratch.parent.is_dir():
        raise ValueError("Scratch must be new, with an existing parent")
    scratch.mkdir()
    canary = scratch / "canary.txt"
    canary.write_bytes(b"X38 unrelated synthetic file\n")
    sys.path.insert(0, str(repo))
    import schedule
    rows = [run_case(schedule, c, manifest["policy"], oracle["expected"][c["id"]], scratch) for c in manifest["cases"]]
    origins = {}
    for name, module in list(sys.modules.items()):
        if name == "schedule" or name.startswith("schedule."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(repo / "schedule"):
                raise ValueError("Import escapes reviewed package")
            origins[name] = path.relative_to(repo).as_posix()
    if capture_scope(repo) != scope or canary.read_bytes() != b"X38 unrelated synthetic file\n":
        raise ValueError("Code or unrelated synthetic file changed")
    return {"code_scope": scope, "module_origins": origins, "tests": rows,
            "policy": manifest["policy"], "scratch_retained": True,
            "runtime": {"python": platform.python_version(), "platform": sys.platform},
            "sequential_callbacks": True, "threads_network_crash_deadline_tested": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "manifest", "oracle", "scratch"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--oracle-sha256", required=True)
    args = parser.parse_args(argv)
    report = run(args.repo, read_pinned(args.manifest, args.manifest_sha256), read_pinned(args.oracle, args.oracle_sha256), args.scratch)
    report.update(manifest_sha256=args.manifest_sha256, oracle_sha256=args.oracle_sha256,
                  probe_sha256=digest(Path(__file__).read_bytes()))
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if all(t["status"] == "PASS" for t in report["tests"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
