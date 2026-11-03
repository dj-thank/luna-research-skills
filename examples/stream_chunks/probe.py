"""Observe bytes actually returned to a pinned SSE consumer, in delivery order."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


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
        if not isinstance(case, dict) or set(case) != {"id", "file", "cuts"}:
            raise ValueError("Invalid case fields")
        if (not isinstance(case["id"], str) or not re.fullmatch(r"[a-z_]{1,40}", case["id"])
                or case["id"] in seen):
            raise ValueError("Invalid or duplicate case ID")
        seen.add(case["id"])
        if not isinstance(case["file"], str) or not re.fullmatch(r"[a-z-]{1,40}\.bin", case["file"]):
            raise ValueError("Invalid direct payload name")
        cuts = case["cuts"]
        if (not isinstance(cuts, list) or len(cuts) > 32
                or any(type(c) is not int or not 0 < c < 4096 for c in cuts)
                or cuts != sorted(set(cuts))):
            raise ValueError("Invalid chunk cuts")
    if (not isinstance(oracle, dict) or set(oracle) != {"schema_version", "expected"}
            or type(oracle["schema_version"]) is not int or oracle["schema_version"] != 1
            or not isinstance(oracle["expected"], dict) or set(oracle["expected"]) != seen):
        raise ValueError("Oracle must cover the exact cases")
    for value in oracle["expected"].values():
        if (not isinstance(value, dict) or set(value) != {"events", "error_kind"}
                or value["error_kind"] is not None or not isinstance(value["events"], list)):
            raise ValueError("Invalid expected output")
        for event in value["events"]:
            if (not isinstance(event, dict) or set(event) != {"id", "event", "data", "retry"}
                    or any(v is not None and not isinstance(v, str) for v in event.values())):
                raise ValueError("Invalid expected event")
        canonical(value)


def byte_identity(raw):
    return {"type": "bytes", "bytes": len(raw), "sha256": digest(raw), "hex": raw.hex()}


class DeliveredChunks:
    """Capture only pulls actually made by the consumer; do not prefill a trace."""
    def __init__(self, chunks):
        self.pending = iter(chunks)
        self.delivered = []
        self.trace = []
        self.exhausted = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self.pending)
        except StopIteration:
            self.exhausted = True
            raise
        self.trace.append(byte_identity(chunk))
        self.delivered.append(chunk)
        # Return exactly this immutable object, after all upstream transforms.
        return chunk


def observe(module, case, inputs, mode):
    if mode not in ("declared", "coalesce", "reorder", "drop"):
        raise ValueError("Invalid control mode")
    path = inputs / case["file"]
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected an ordinary payload file")
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096 or any(c >= len(raw) for c in case["cuts"]):
        raise ValueError("Oversized payload or cut outside payload")
    points = [0, *case["cuts"], len(raw)]
    chunks = [raw[a:b] for a, b in zip(points, points[1:])]
    if mode == "coalesce":
        chunks = [b"".join(chunks)]
    elif mode == "reorder" and case["id"] == "repeat_fragments":
        chunks[1], chunks[2] = chunks[2], chunks[1]
    elif mode == "drop" and case["id"] == "two_events":
        chunks = chunks[1:]
    stream = DeliveredChunks(chunks)
    events, error_kind, error = [], None, None
    try:
        for event in module.SSEClient(stream).events():
            events.append({key: getattr(event, key) for key in ("id", "event", "data", "retry")})
    except Exception as caught:
        error_kind, error = type(caught).__name__, str(caught)
    return {"actual": {"events": events, "error_kind": error_kind},
            "input": {"path": case["file"], "bytes": len(raw), "sha256": digest(raw)},
            "buffer": byte_identity(b"".join(stream.delivered)),
            "delivery": {"chunks": stream.trace, "exhausted": stream.exhausted}, "error": error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "inputs", "manifest", "oracle"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("manifest-sha256", "oracle-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--mode", choices=("declared", "coalesce", "reorder", "drop"), default="declared")
    args = parser.parse_args()
    manifest = read_pinned(args.manifest, args.manifest_sha256)
    oracle = read_pinned(args.oracle, args.oracle_sha256)
    validate(manifest, oracle)
    source = args.repo.resolve()
    path = source / "sseclient/__init__.py"
    scope = {"sseclient/__init__.py": digest(path.read_bytes())}
    if "sseclient" in sys.modules:
        raise ValueError("Run in a fresh interpreter")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("sseclient", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sseclient"] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != path:
        raise ValueError("Unpinned target module")
    rows = []
    for case in manifest["cases"]:
        row = observe(module, case, args.inputs, args.mode)
        row.update(id=case["id"], status="PASS" if canonical(row["actual"]) == canonical(oracle["expected"][case["id"]]) else "FAIL")
        rows.append(row)
    if scope != {"sseclient/__init__.py": digest(path.read_bytes())}:
        raise ValueError("Source changed during observation")
    result = {"schema_version": 1, "code_scope": scope, "imported_target_modules": {"sseclient": "sseclient/__init__.py"},
              "mode": args.mode, "probe_sha256": digest(Path(__file__).read_bytes()),
              "manifest_sha256": args.manifest_sha256, "oracle_sha256": args.oracle_sha256,
              "runtime": {"implementation": sys.implementation.name, "version": list(sys.version_info[:3])},
              "tests": rows}
    for key, field in (("outputs", "actual"), ("inputs", "input"), ("buffers", "buffer"), ("deliveries", "delivery")):
        result["actual_" + key] = {row["id"]: row[field] for row in rows}
    print(canonical(result))
    return int(any(row["status"] != "PASS" for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
