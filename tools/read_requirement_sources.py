#!/usr/bin/env python3
"""Read requirements from explicitly named, pinned, stable JSON source registers.

Read-only and offline. Agreement is neither approval nor evidence of source
independence, truth, freshness, or complete requirement selection.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True
import read_evidence as E
import read_requirements as R

MAX_AGE_SECONDS = 315537897599  # Full span of the supported UTC calendar.


def validate_question(question):
    fields = {"schema_version", "question_id", "question", "subject",
              "sources", "max_source_bytes", "max_result_bytes", "requirements"}
    if type(question) is dict and question.get("schema_version") in (2, 3):
        fields.update(("as_of", "time_constraints"))
        if question["schema_version"] == 3:
            fields.add("freshness_constraints")
    R.fields(question, fields)
    R.version(question, (1, 2, 3))
    R.identifier(question["question_id"]); R.identifier(question["subject"])
    text = question["question"]
    if type(text) is not str or not text.strip() or len(text) > 4096:
        raise ValueError("question must contain 1 to 4096 characters")
    for name in ("max_source_bytes", "max_result_bytes"):
        if type(question[name]) is not int or not 1 <= question[name] <= E.DOCUMENT_LIMIT:
            raise ValueError(name + " must be an integer from 1 to 4194304")
    sources = question["sources"]
    if type(sources) is not list or not 2 <= len(sources) <= 8:
        raise ValueError("expected 2 to 8 declared sources")
    source_ids = set()
    for source in sources:
        R.fields(source, {"id", "sha256"})
        R.identifier(source["id"]); E.pin(source["sha256"])
        if source["id"] in source_ids:
            raise ValueError("source IDs must be unique")
        source_ids.add(source["id"])
    rows = question["requirements"]
    if type(rows) is not list or not 1 <= len(rows) <= 32:
        raise ValueError("expected 1 to 32 requirements")
    ids, purposes, used_sources = set(), set(), set()
    for row in rows:
        R.fields(row, {"id", "purpose", "sources"})
        R.identifier(row["id"])
        if row["id"] in ids:
            raise ValueError("requirement IDs must be unique")
        if type(row["purpose"]) is not str or row["purpose"] not in ("answer", "guard"):
            raise ValueError("requirement purpose must be answer or guard")
        required = row["sources"]
        if type(required) is not list or not 1 <= len(required) <= 8:
            raise ValueError("each requirement needs 1 to 8 sources")
        for source_id in required:
            R.identifier(source_id)
        if len(set(required)) != len(required) or not set(required) <= source_ids:
            raise ValueError("requirement sources must be unique declared IDs")
        ids.add(row["id"]); purposes.add(row["purpose"]); used_sources.update(required)
    if purposes != {"answer", "guard"}:
        raise ValueError("question needs both answer and guard requirements")
    if used_sources != source_ids:
        raise ValueError("every declared source must serve a requirement")
    if question["schema_version"] in (2, 3):
        timestamp(question["as_of"])
        constraints = question["time_constraints"]
        if type(constraints) is not list or not 1 <= len(constraints) <= 32:
            raise ValueError("expected 1 to 32 time constraints")
        constraint_ids = set()
        for row in constraints:
            R.fields(row, {"id", "requirement", "valid_from", "valid_until"})
            R.identifier(row["id"]); R.identifier(row["requirement"])
            if row["id"] in constraint_ids or row["requirement"] not in ids:
                raise ValueError("time constraints need unique IDs and declared requirements")
            constraint_ids.add(row["id"])
            E.tokens(row["valid_from"]); E.tokens(row["valid_until"])
            if row["valid_from"] == row["valid_until"]:
                raise ValueError("interval pointers must be distinct")
    if question["schema_version"] == 3:
        constraints = question["freshness_constraints"]
        if type(constraints) is not list or not 1 <= len(constraints) <= 32:
            raise ValueError("expected 1 to 32 freshness constraints")
        constraint_ids = set()
        for row in constraints:
            R.fields(row, {"id", "requirement", "observed_at", "max_age_seconds"})
            R.identifier(row["id"]); R.identifier(row["requirement"])
            if row["id"] in constraint_ids or row["requirement"] not in ids:
                raise ValueError("freshness constraints need unique IDs and declared requirements")
            constraint_ids.add(row["id"])
            E.tokens(row["observed_at"])
            if type(row["max_age_seconds"]) is not int or not 0 <= row["max_age_seconds"] <= MAX_AGE_SECONDS:
                raise ValueError("max_age_seconds must be an integer from 0 to 315537897599")


def timestamp(value):
    """Deliberately narrow UTC format; never consult the host clock or timezone."""
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        raise ValueError("expected a valid UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def check_time(question, selected):
    # All observations of a selected requirement have identical typed values;
    # preserve every observation/qualifier in the eventual complete response.
    values = {r["id"]: r["observations"][0]["value"] for r in selected}
    as_of = timestamp(question["as_of"])
    gaps = []
    for row in question["time_constraints"]:
        reason = None
        try:
            start, end = [E.select(values[row["requirement"]], row[key])
                          for key in ("valid_from", "valid_until")]
        except ValueError:
            reason = "MISSING"
        else:
            if start is None or end is None:
                reason = "UNKNOWN"
            else:
                try:
                    start, end = timestamp(start), timestamp(end)
                except ValueError:
                    reason = "TIME_FORMAT"
                else:
                    if start >= end:
                        reason = "INVALID_INTERVAL"
                    elif as_of < start:
                        reason = "NOT_YET_VALID"
                    elif as_of >= end:
                        reason = "EXPIRED"
        if reason:
            gaps.append(dict(id=row["id"], requirement=row["requirement"], reason=reason))
    return gaps


def check_freshness(question, selected):
    """Check the declared observation, never forwarding time or the host clock."""
    values = {r["id"]: r["observations"][0]["value"] for r in selected}
    as_of = timestamp(question["as_of"])
    gaps, checks = [], []
    for row in question["freshness_constraints"]:
        reason = None
        try:
            observed = E.select(values[row["requirement"]], row["observed_at"])
        except ValueError:
            reason = "MISSING"
        else:
            if observed is None:
                reason = "UNKNOWN"
            else:
                try:
                    delta = as_of - timestamp(observed)
                except ValueError:
                    reason = "TIME_FORMAT"
                else:
                    # UTC whole seconds: exact integer arithmetic, including negatives.
                    age = delta.days * 86400 + delta.seconds
                    if age < 0:
                        reason = "FUTURE_OBSERVATION"
                    elif age > row["max_age_seconds"]:
                        reason = "STALE"
        if reason:
            gaps.append(dict(id=row["id"], requirement=row["requirement"], reason=reason))
        else:
            checks.append(dict(id=row["id"], requirement=row["requirement"], status="WITHIN_MAX_AGE",
                               age_seconds=age, max_age_seconds=row["max_age_seconds"]))
    return gaps, checks


def bind_paths(bindings, expected_ids):
    # Accept pairs so repeated CLI names cannot silently overwrite a prior path.
    if type(bindings) not in (list, tuple):
        raise ValueError("source paths must be explicit ID/path pairs")
    paths = {}
    for pair in bindings:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            raise ValueError("expected a source ID/path pair")
        source_id, path = pair
        R.identifier(source_id)
        if source_id not in expected_ids or source_id in paths:
            raise ValueError("duplicate or undeclared source binding")
        paths[source_id] = Path(path)
    if set(paths) != expected_ids:
        raise ValueError("missing declared source binding")
    return paths


def read_sources(question_path, expected_question_sha256, source_bindings):
    metrics = dict(question_reads=0, question_bytes_read=0, source_reads=0, source_bytes_read=0)
    try:
        E.pin(expected_question_sha256)
        raw = E.read_regular(question_path, E.REQUEST_LIMIT, metrics, "question")
        if E.digest(raw) != expected_question_sha256:
            raise ValueError("question differs from the caller pin")
        question = E.load_json(raw)
        validate_question(question)
        paths = bind_paths(source_bindings, {s["id"] for s in question["sources"]})
        documents, origins = {}, {}
        for source in question["sources"]:
            remaining = question["max_source_bytes"] - metrics["source_bytes_read"]
            raw_source = E.read_regular(paths[source["id"]], remaining, metrics, "source")
            actual = E.digest(raw_source)
            if actual != source["sha256"]:
                raise ValueError("source differs from the approved pin: " + source["id"])
            document = E.load_json(raw_source)
            R.validate_source(document)
            documents[source["id"]] = document["observations"]
            origins[source["id"]] = {"id": source["id"], "sha256": actual}
        selected, gaps = [], []
        for requirement in question["requirements"]:
            matches, missing = [], []
            for source_id in requirement["sources"]:
                records = [row for row in documents[source_id]
                           if row["subject"] == question["subject"] and row["requirement"] == requirement["id"]]
                if not records:
                    missing.append(source_id)
                matches.extend(dict(row, origin=origins[source_id]) for row in records)
            # An unrelated/successful record cannot cover another required source.
            if missing:
                gaps.append(dict(id=requirement["id"], reason="MISSING_SOURCE", sources=missing))
            elif any(row["state"] == "unknown" or row["value"] is None for row in matches):
                gaps.append(dict(id=requirement["id"], reason="UNKNOWN"))
            elif len({E.encode(row["value"]) for row in matches}) != 1:
                gaps.append(dict(id=requirement["id"], reason="CONFLICT"))
            else:
                selected.append(dict(requirement, observations=matches))
        has_time = question["schema_version"] in (2, 3)
        has_freshness = question["schema_version"] == 3
        time_gaps = check_time(question, selected) if has_time and not gaps else []
        freshness_gaps, freshness_checks = check_freshness(question, selected) if has_freshness and not (gaps or time_gaps) else ([], [])
        result = dict(schema_version=1, status="INSUFFICIENT" if gaps or time_gaps or freshness_gaps else "OBSERVED",
                      scope="declared_requirements_and_sources_only", question_id=question["question_id"],
                      subject=question["subject"], question_sha256=expected_question_sha256,
                      sources=list(origins.values()), metrics=metrics)
        if has_time:
            result.update(as_of=question["as_of"], scope="declared_requirements_sources_and_time_only")
        if has_freshness:
            result["scope"] = "declared_requirements_sources_time_and_freshness_only"
        if gaps:
            result["gaps"] = gaps
        elif time_gaps:
            result["time_gaps"] = time_gaps
        elif freshness_gaps:
            result["freshness_gaps"] = freshness_gaps
        else:
            result["requirements"] = selected
            if has_time:
                result["time_checks"] = [dict(id=r["id"], requirement=r["requirement"], status="COVERS_AS_OF")
                                         for r in question["time_constraints"]]
            if has_freshness:
                result["freshness_checks"] = freshness_checks
            if len(E.encode(result)) > question["max_result_bytes"]:
                raise ValueError("result byte limit exceeded; never truncate required evidence")
        return result
    except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        return dict(schema_version=1, status="REFUSED", error=str(exc), metrics=metrics)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="independently reviewed question digest")
    parser.add_argument("--source", nargs=2, action="append", required=True, metavar=("ID", "PATH"),
                        help="explicit source binding; repeat once for every declared ID")
    args = parser.parse_args(argv)
    result = read_sources(args.question, args.sha256, args.source)
    sys.stdout.write(E.encode(result).decode("utf-8"))
    return {"OBSERVED": 0, "INSUFFICIENT": 1, "REFUSED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
