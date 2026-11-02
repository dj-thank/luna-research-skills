#!/usr/bin/env python3
"""Read-only, advisory next-batch snapshot for flat project v2 ledgers."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys

# Sibling imports must not create cache files in a read-only advisory command.
sys.dont_write_bytecode = True

VERSION = "1.1"
TERMINAL = {"completed", "failed", "timed_out", "abandoned", "not_dispatched"}
WRITERS = {"builder", "operator"}
# Candidate reviewers do not satisfy Project's final-verifier closure reserve.
RESERVE = {"verifier"}
_spec = importlib.util.spec_from_file_location("swarm_setup", Path(__file__).with_name("check_setup.py"))
assert _spec and _spec.loader
CHECK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CHECK)


def timestamp(value):
    return CHECK._parse_timestamp(value)


def reason(code, related=()):
    return {"code": code, "related_attempt_ids": list(related)}


def validate(ledger, specialist_model=CHECK.DEFAULT_SPECIALIST_MODEL):
    """Use the checker's in-memory v2 entry points; never reopen the input."""
    if specialist_model not in CHECK.SUPPORTED_SPECIALIST_MODELS:
        raise ValueError("unsupported specialist_model: " + repr(specialist_model))
    # Each validation owns its checker policy. Never mutate the shared default
    # module or derive the selected profile from untrusted ledger receipts.
    check = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(check)
    check.EXPECTED_MODEL = specialist_model
    if not isinstance(ledger, dict):
        return ["ledger must be an object"], []
    if ledger.get("ledger_type") != "project" or type(ledger.get("version")) is not int or ledger["version"] != 2:
        return ["only project version 2 is supported"], []
    settings = ledger.get("tree", ledger)
    if not isinstance(settings, dict) or settings.get("mode", "flat") != "flat":
        return ["only flat project mode is supported"], []
    rows, errors = check._resolve_assignment_rows(ledger)
    if errors:
        return errors, []
    if any(not isinstance(r, dict) for r in rows):
        return ["attempts must be objects"], []
    if any(r.get("parent_attempt_id") is not None or r.get("depth") != 1
           or check._logical_coordinator(r) or r.get("may_spawn_descendants")
           or r.get("descendant_budget", 0) != 0 for r in rows):
        return ["only flat leaf attempts without descendant grants are supported"], []
    with contextlib.redirect_stdout(io.StringIO()):
        errors, warnings = check._validate_tree_ledger(ledger, project=True)
        errors.extend(check._validate_project_v2_contract(ledger))
    for row in rows:
        if "planned_at" in row and timestamp(row["planned_at"]) is None:
            errors.append(f"{row.get('attempt_id')}: planned_at must have timezone")
    return errors, warnings


def overlaps(a, b):
    paths = lambda row: [CHECK._ownership_path(p) for p in row["ownership"]
                         if p.strip().casefold() != "read-only"]
    return any(x[:2] == y[:2] and (x[2][:len(y[2])] == y[2] or y[2][:len(x[2])] == x[2])
               for x in paths(a) for y in paths(b))


def plan(ledger, open_children, now, *, specialist_model=CHECK.DEFAULT_SPECIALIST_MODEL):
    if type(open_children) is not int or open_children < 0:
        raise ValueError("open_children must be a non-negative integer")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must have timezone")
    errors, warnings = validate(ledger, specialist_model)
    if errors:
        return {"schema_version": 1, "advisory_only": True,
                "errors": [{"code": "INVALID_LEDGER", "message": e} for e in errors]}
    rows, _ = CHECK._resolve_assignment_rows(ledger)
    settings = ledger.get("tree", ledger)
    get = lambda long, short: settings.get(long, settings.get(short))
    budget, cap, width = get("attempt_budget_N", "N"), get("concurrency_cap_C", "C"), get("wave_width_W", "W")
    reserve = settings.get("verifier_reserve_V", settings.get("verifier_reserve", 0))
    by_id = {r["attempt_id"]: r for r in rows}
    end = lambda r: timestamp(r.get("finished_at")) or timestamp(r.get("timeout_at"))
    active = [r for r in rows if r["execution_status"] == "started" or
              (r["execution_status"] not in {"planned", "not_dispatched"}
               and end(r) is not None and end(r) > now)]
    used = sum(r["execution_status"] not in {"planned", "not_dispatched"} for r in rows)
    remaining = budget - used
    reserve_left = max(0, reserve - sum(r["kind"] in RESERVE and r["acceptance_status"] == "accepted"
                                      and end(r) is not None and end(r) <= now for r in rows))
    # In-flight reserve work already occupies an attempt; failure is still unknown.
    reserve_inflight = sum(r["kind"] in RESERVE for r in active)
    effective = max(open_children, len(active))
    slots = max(0, min(width, cap - effective))
    pending = [r["attempt_id"] for r in rows if r["execution_status"] == "completed"
               and r["acceptance_status"] == "accepted" and r["integration_status"] == "pending"
               and end(r) is not None and end(r) <= now]
    selected, blocked, alerts = [], [], []
    live_writers = [r for r in rows if r["kind"] in WRITERS and
                    (r["execution_status"] == "started" or
                     (r["execution_status"] in TERMINAL and end(r) is not None and end(r) > now))]
    overall = timestamp(settings.get("overall_deadline", ledger.get("overall_deadline")))
    def expiration(r):
        result = []
        if overall and now >= overall:
            result.append(reason("OVERALL_DEADLINE_EXPIRED"))
        if timestamp(r.get("deadline")) and now >= timestamp(r["deadline"]):
            result.append(reason("DEADLINE_EXPIRED"))
        if r.get("ttl_seconds") and timestamp(r.get("started_at")) and now >= timestamp(r["started_at"]) + timedelta(seconds=r["ttl_seconds"]):
            result.append(reason("ACTIVE_TTL_EXPIRED"))
        return result
    for r in active:
        active_reasons = expiration(r)
        if r["execution_status"] != "started":
            active_reasons.append(reason("RECORDED_FINISH_AFTER_SNAPSHOT"))
        if active_reasons:
            alerts.append({"attempt_id": r["attempt_id"], "reasons": active_reasons})
    selected_reserve = 0
    for r in rows:
        if r["execution_status"] != "planned":
            continue
        reasons = expiration(r)
        if timestamp(r.get("planned_at")) and timestamp(r["planned_at"]) > now:
            reasons.append(reason("PLANNED_AT_FUTURE"))
        for dep in r.get("dependencies", []):
            d = by_id[dep]
            if d["execution_status"] in TERMINAL and d["execution_status"] != "completed":
                reasons.append(reason("DEPENDENCY_FAILED", [dep]))
            elif d["execution_status"] != "completed" or d["acceptance_status"] not in (
                    {"pending", "accepted"} if r["kind"] == "reviewer" else {"accepted"}):
                reasons.append(reason("DEPENDENCY_NOT_ACCEPTED", [dep]))
            elif end(d) is None or end(d) > now:
                reasons.append(reason("DEPENDENCY_FINISH_FUTURE", [dep]))
        if r.get("retry_of"):
            d = by_id[r["retry_of"]]
            if d["execution_status"] not in TERMINAL or end(d) is None or end(d) > now:
                reasons.append(reason("RETRY_PREDECESSOR_NOT_FINISHED", [d["attempt_id"]]))
            if d["acceptance_status"] == "accepted":
                reasons.append(reason("RETRY_ACCEPTED_PREDECESSOR", [d["attempt_id"]]))
        if r["kind"] == "verifier":
            if ledger["root_integration_status"] != "completed" or not ledger.get("root_integration_receipt"):
                reasons.append(reason("ROOT_INTEGRATION_REQUIRED"))
            unfinished = [d["attempt_id"] for d in rows if d["kind"] != "verifier"
                          and (d["execution_status"] not in TERMINAL or d["acceptance_status"] == "pending"
                               or end(d) is None or end(d) > now)]
            if unfinished:
                reasons.append(reason("NON_VERIFIER_WORK_UNFINISHED", unfinished))
            unintegrated = [d["attempt_id"] for d in rows if d["kind"] in WRITERS
                            and d["acceptance_status"] == "accepted" and d["integration_status"] != "integrated"]
            if unintegrated:
                reasons.append(reason("ACCEPTED_WRITERS_NOT_INTEGRATED", unintegrated))
        if r.get("access_mode") == "root_only":
            reasons.append(reason("ROOT_ONLY_WORK"))
        if r["kind"] in WRITERS:
            conflicts = [d["attempt_id"] for d in live_writers if overlaps(r, d)]
            if conflicts:
                reasons.append(reason("WRITER_OWNERSHIP_CONFLICT", conflicts))
        if len(selected) >= slots:
            reasons.append(reason("CAPACITY_OR_WAVE_LIMIT"))
        available = remaining - len(selected)
        if available <= 0:
            reasons.append(reason("ATTEMPT_BUDGET_EXHAUSTED"))
        elif r["kind"] not in RESERVE and available <= max(0, reserve_left - reserve_inflight - selected_reserve):
            reasons.append(reason("VERIFIER_RESERVE_PROTECTED"))
        if reasons:
            blocked.append({"attempt_id": r["attempt_id"], "reasons": reasons})
        else:
            selected.append(r["attempt_id"])
            if r["kind"] in WRITERS:
                live_writers.append(r)
            if r["kind"] in RESERVE:
                selected_reserve += 1
    return {"schema_version": 1, "advisory_only": True, "now": now.isoformat(),
            "next_wave": 1 + max((r["wave"] for r in rows if r["execution_status"] not in {"planned", "not_dispatched"}), default=0),
            "selected_attempt_ids": selected, "blocked": blocked,
            "active_attempt_ids": [r["attempt_id"] for r in active], "active_alerts": alerts,
            "integration_pending_attempt_ids": pending,
            "capacity": {"ledger_attempts_used": used, "ledger_attempts_remaining": remaining,
                         "recorded_active_count": len(active), "supplied_open_children": open_children,
                         "effective_open_children": effective, "concurrency_cap": cap,
                         "available_slots": slots, "wave_width": width,
                         "verifier_reserve_remaining": reserve_left},
            "required_checks": ["FINAL_TRACE_PREFLIGHT_BEFORE_EVERY_SPEND_OR_FOLLOWUP",
                                "LIVE_CONFIGURED_CAP_AND_RUNTIME_PROOF",
                                "ROOT_CONFIRM_ACTUAL_WRITER_RELEASE_BEFORE_REASSIGNMENT",
                                "ROOT_REOPEN_ACCEPTANCE_AND_INTEGRATION_RECEIPTS"],
            "warnings": warnings}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--version", action="version", version=VERSION)
        parser.add_argument("--ledger-json", type=Path, required=True)
        parser.add_argument("--open-children", type=int, required=True)
        parser.add_argument("--now")
        parser.add_argument("--specialist-model", choices=CHECK.SUPPORTED_SPECIALIST_MODELS,
                            default=CHECK.DEFAULT_SPECIALIST_MODEL,
                            help="Explicit terminal profile; Luna by default, both profiles use low effort.")
        args = parser.parse_args(argv)
        now = timestamp(args.now) if args.now else datetime.now(timezone.utc)
        # One read: validation and planning use the same parsed bytes.
        ledger = json.loads(args.ledger_json.read_bytes().decode("utf-8"))
        output = plan(ledger, args.open_children, now, specialist_model=args.specialist_model)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError) as exc:
        output = {"schema_version": 1, "advisory_only": True,
                  "errors": [{"code": "INVALID_INPUT", "message": str(exc)}]}
    print(json.dumps(output, ensure_ascii=True, sort_keys=True))
    return 2 if "errors" in output else 0


if __name__ == "__main__":
    raise SystemExit(main())
