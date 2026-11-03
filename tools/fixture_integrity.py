"""Check trusted, independent-case builders before freezing benchmark fixtures.

This is an in-process test helper, not a sandbox or a semantic oracle.
"""
from __future__ import annotations

import hashlib
import json


def _encode(value, depth=0):
    def validate(item, level):
        if level > 64:
            raise ValueError("JSON nesting exceeds 64")
        if type(item) in (str, int, float, bool) or item is None:
            return
        if type(item) is list:
            for child in item:
                validate(child, level + 1)
        elif type(item) is dict and all(type(k) is str for k in item):
            for child in item.values():
                validate(child, level + 1)
        else:
            raise ValueError("use JSON types and string object keys")
    validate(value, depth)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _index(rows, case_ids):
    if type(rows) is not list:
        raise ValueError("builder must return a list")
    result = {}
    for row in rows:
        if type(row) is not dict or set(row) != {"id", "input", "expected"}:
            raise ValueError("each case requires exactly id, input and expected")
        case_id = row["id"]
        if type(case_id) is not str or case_id not in case_ids or case_id in result:
            raise ValueError("unexpected or repeated case id")
        result[case_id] = _encode(row).decode("utf-8")
    if set(result) != set(case_ids):
        raise ValueError("missing case ids")
    return result


def check_builder(build, case_ids, expected_cases):
    """Compare four constructions with a separately reviewed full-case oracle.

    build(order) must reset its own per-build state and return a list of JSON
    {id, input, expected} records. It runs in the caller's process. Only pass
    trusted, bounded, side-effect-free builders. Event order *within* each case
    remains significant. Mapping insertion order and outer case order do not.
    """
    if type(case_ids) not in (list, tuple) or len(case_ids) < 2:
        raise ValueError("at least two independent case ids are required")
    if any(type(x) is not str or not x for x in case_ids) or len(set(case_ids)) != len(case_ids):
        raise ValueError("case ids must be unique nonempty strings")
    ids = tuple(case_ids)
    oracle = _index(expected_cases, ids)  # Capture before invoking the builder.
    orders = (("forward", ids), ("reverse", ids[::-1]),
              ("rotate", ids[1:] + ids[:1]), ("repeat-forward", ids))
    snapshots, errors, mismatches = {}, [], []
    for name, order in orders:
        try:
            snapshots[name] = _index(build(order), ids)
        except Exception as exc:
            # A bad build cannot become a successful partial snapshot.
            errors.append({"order": name, "error_type": type(exc).__name__})
            continue
        bad = [i for i in ids if snapshots[name][i] != oracle[i]]
        if bad:
            mismatches.append({"order": name, "case_ids": bad})
    changes = []
    if not errors:
        for name, _ in orders[1:]:
            bad = [i for i in ids if snapshots[name][i] != snapshots["forward"][i]]
            if bad:
                changes.append({"order": name, "case_ids": bad})
    passed = not errors and not mismatches and not changes
    digest = lambda value: hashlib.sha256(_encode(value)).hexdigest()
    return {
        "status": "CONSISTENT" if passed else "MISMATCH",
        "passes": passed,
        "builder_calls": len(orders),
        "case_count": len(ids),
        "order_independent": None if errors else not changes,
        "matches_reviewed_cases": not errors and not mismatches,
        "oracle_sha256": digest(oracle),
        "snapshot_sha256": {name: digest(value) for name, value in snapshots.items()},
        "order_changes": changes,
        "oracle_mismatches": mismatches,
        "build_errors": errors,
    }
