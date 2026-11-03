"""Run trusted Boltons update code against pinned ordered-record answers."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

sys.dont_write_bytecode = True
FILES = ["__init__.py", "cacheutils.py", "debugutils.py", "deprutils.py", "dictutils.py",
         "easterutils.py", "ecoutils.py", "excutils.py", "fileutils.py", "formatutils.py",
         "funcutils.py", "gcutils.py", "ioutils.py", "iterutils.py", "jsonutils.py",
         "listutils.py", "mathutils.py", "mboxutils.py", "namedutils.py", "pathutils.py",
         "queueutils.py", "setutils.py", "socketutils.py", "statsutils.py", "strutils.py",
         "tableutils.py", "tbutils.py", "timeutils.py", "typeutils.py", "urlutils.py"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, pin):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != pin:
        raise ValueError("Input size or independently supplied pin differs")
    return json.loads(raw)


def valid_pairs(value):
    return isinstance(value, list) and len(value) <= 16 and all(
        isinstance(pair, list) and len(pair) == 2 and all(isinstance(v, str) and len(v) <= 128 for v in pair)
        for pair in value)


def validate(manifest, oracle):
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "cases"} or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unknown manifest schema")
    if not isinstance(oracle, dict) or set(oracle) != {"schema_version", "expected"} or type(oracle["schema_version"]) is not int or oracle["schema_version"] != 1 or not isinstance(oracle["expected"], dict):
        raise ValueError("Unknown oracle schema")
    if not isinstance(manifest["cases"], list) or not 1 <= len(manifest["cases"]) <= 24:
        raise ValueError("Expected bounded cases")
    seen = set()
    for case in manifest["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "source", "initial", "pairs", "keywords"}:
            raise ValueError("Unknown case fields")
        key = case["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) or key in seen:
            raise ValueError("Unsafe or duplicate case ID")
        seen.add(key)
        if case["source"] not in ("list", "iterator", "omd") or not valid_pairs(case["initial"]) or not valid_pairs(case["pairs"]):
            raise ValueError("Invalid source or bounded string pairs")
        kw = case["keywords"]
        if not isinstance(kw, dict) or len(kw) > 16 or any(not isinstance(k, str) or not isinstance(v, str) or max(len(k), len(v)) > 128 for k, v in kw.items()):
            raise ValueError("Invalid keywords")
        expected = oracle["expected"].get(key)
        if not isinstance(expected, dict) or set(expected) != {"unique_keys", "pairs", "query"} or type(expected["unique_keys"]) is not int or not 0 <= expected["unique_keys"] <= 32 or not valid_pairs(expected["pairs"]) or not isinstance(expected["query"], str):
            raise ValueError("Invalid complete oracle")
    if seen != set(oracle["expected"]):
        raise ValueError("Oracle and manifest cases differ")


def capture_scope(repo):
    folder = repo / "boltons"
    paths = sorted(folder.rglob("*.py"))
    if sorted(p.relative_to(folder).as_posix() for p in paths) != sorted(FILES) or any(folder.rglob("*.pyc")) or any(folder.rglob("*.pyo")):
        raise ValueError("Unexpected package inventory or bytecode cache")
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError("Source escapes reviewed package")
    return {p.relative_to(repo).as_posix(): digest(p.read_bytes()) for p in paths}


def expected_counts(case, expected):
    return {"unique_keys": expected["unique_keys"], "return": None, "error": None,
            "input_unchanged": True, "iterator_yields": len(case["pairs"]) if case["source"] == "iterator" else None}


def observe(case, kind, mapping_type):
    mapping = mapping_type([tuple(pair) for pair in case["initial"]])
    supplied = [tuple(pair) for pair in case["pairs"]]
    original = list(supplied)
    yields = 0

    def iterator():
        nonlocal yields
        for pair in supplied:
            yields += 1
            yield pair

    source = iterator() if case["source"] == "iterator" else mapping_type(supplied) if case["source"] == "omd" else supplied
    error = None
    result = None
    try:
        result = mapping.update(source, **case["keywords"])
    except Exception as exc:
        error = type(exc).__name__
    return {"counts": {"unique_keys": len(mapping), "return": result, "error": error,
                       "input_unchanged": supplied == original,
                       "iterator_yields": yields if case["source"] == "iterator" else None},
            "records": {"pairs": [list(pair) for pair in mapping.items(multi=True)],
                        "query": mapping.to_text(full_quote=True) if kind == "query" else None}}


def run(repo, manifest, oracle):
    validate(manifest, oracle)
    repo = repo.resolve()
    scope = capture_scope(repo)
    if any(n == "boltons" or n.startswith("boltons.") for n in sys.modules):
        raise ValueError("Use a fresh process")
    sys.path.insert(0, str(repo))
    from boltons.dictutils import OrderedMultiDict
    from boltons.urlutils import QueryParamDict
    rows = []
    for kind, mapping_type in (("omd", OrderedMultiDict), ("query", QueryParamDict)):
        for case in manifest["cases"]:
            wanted = oracle["expected"][case["id"]]
            observed = observe(case, kind, mapping_type)
            counts_ok = observed["counts"] == expected_counts(case, wanted)
            records_ok = observed["records"] == {"pairs": wanted["pairs"], "query": wanted["query"] if kind == "query" else None}
            rows.append({"id": kind + ":" + case["id"], **observed,
                         "count_status": "PASS" if counts_ok else "FAIL",
                         "record_status": "PASS" if records_ok else "FAIL",
                         "status": "PASS" if counts_ok and records_ok else "FAIL"})
    origins = {}
    for name, module in list(sys.modules.items()):
        if name == "boltons" or name.startswith("boltons."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(repo / "boltons"):
                raise ValueError("Import escapes reviewed package")
            origins[name] = path.relative_to(repo).as_posix()
    if capture_scope(repo) != scope:
        raise ValueError("Reviewed code changed during execution")
    return {"code_scope": scope, "module_origins": origins, "tests": rows,
            "runtime": {"python": platform.python_version(), "platform": sys.platform},
            "network_or_installation_performed": False}


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
