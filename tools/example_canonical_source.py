"""Compare preparation routes on six frozen Git fixtures (source-only)."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import prepare_source_snapshot as S
from read_evidence import encode

ORACLE = Path(__file__).resolve().parent / "fixtures/canonical_source_oracle.json"

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def git(repo, *args, input=None, profile="lf"):
    settings = {"lf": ("false", "lf"), "crlf": ("true", "lf"), "eol": ("false", "crlf")}[profile]
    env = S.git_environment()
    env.update(GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
               GIT_AUTHOR_DATE="2020-01-01T00:00:00+0000", GIT_COMMITTER_DATE="2020-01-01T00:00:00+0000")
    run = subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=" + settings[0],
                          "-c", "core.eol=" + settings[1], "-c", "core.hooksPath=" + os.devnull,
                          *args], input=input, capture_output=True, env=env, timeout=30)
    if run.returncode:
        raise RuntimeError(run.stderr.decode("utf-8", errors="replace"))
    return run.stdout

def fixture(folder, oracle):
    repo = folder / "repo"; repo.mkdir()
    git(repo, "init", "-q", "-b", "main", "--object-format=sha1", "--template=")
    original = {name: bytes.fromhex(row["hex"]) for name, row in oracle["files"].items()}
    for name, raw in original.items():
        path = repo / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes.fromhex(oracle["base_task_hex"]) if name == "src/task.py" else raw)
    git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD").decode().strip()
    (repo / "src/task.py").write_bytes(original["src/task.py"])
    git(repo, "add", "."); git(repo, "commit", "-qm", "fixed")
    fixed = git(repo, "rev-parse", "HEAD").decode().strip()
    (repo / "src/task.py").write_bytes(bytes.fromhex(oracle["mutated_task_hex"]))
    git(repo, "add", "."); git(repo, "commit", "-qm", "changed")
    changed = git(repo, "rev-parse", "HEAD").decode().strip()
    return repo, {"base": base, "fixed": fixed, "changed": changed}, original

def manifest(commit, oracle):
    return {"schema_version": 1, "commit": commit, "files": [
        {"path": name, "mode": row["mode"], "bytes": len(bytes.fromhex(row["hex"])), "sha256": digest(bytes.fromhex(row["hex"]))}
        for name, row in sorted(oracle["files"].items())]}

def compare(folder, oracle_path=ORACLE):
    raw_oracle = oracle_path.read_bytes()
    oracle = json.loads(raw_oracle)
    repo, heads, gold = fixture(folder, oracle)
    rows = []
    for case in oracle["cases"]:
        checkout = folder / (case["id"] + "-checkout")
        git(repo, "worktree", "add", "--detach", str(checkout), heads["base"], profile=case["profile"])
        # The baseline applies the selected patch through the chosen checkout profile.
        patch = git(repo, "diff", heads["base"], heads[case["revision"]])
        git(checkout, "apply", "-", input=patch, profile=case["profile"])
        actual = {name: (checkout / name).read_bytes() for name in gold}
        normalized = {name: data.replace(b"\r\n", b"\n").replace(b"\r", b"\n") for name, data in actual.items()}
        request = manifest(heads[case["revision"]], oracle)
        request_path = folder / (case["id"] + "-manifest.json")
        request_path.write_bytes(encode(request))
        target = folder / (case["id"] + "-canonical")
        before = {name: (checkout / name).read_bytes() for name in gold}
        result = S.prepare(checkout, request_path, digest(request_path.read_bytes()), target, apply=True)
        if result["status"] == "EXPORTED":
            exported = {name: (target / name).read_bytes() for name in gold}
            assert exported == gold
        else:
            assert result["status"] == "REFUSED" and not target.exists()
        assert {name: (checkout / name).read_bytes() for name in gold} == before
        decisions = {"checkout": actual == gold, "canonical": result["status"] == "EXPORTED",
                     "normalize": normalized == gold}
        rows.append({"id": case["id"], "expected": case["accept"], "decisions": decisions,
                     "checkout_sha256": {n: digest(v) for n, v in actual.items()},
                     "canonical_status": result["status"], "source_unchanged": True,
                     "canonical_target_created": target.exists()})
    for policy, expected in oracle["expected"].items():
        assert [row["decisions"][policy] for row in rows] == expected, (policy, rows)
    return {"schema_version": 1, "oracle_sha256": digest(raw_oracle), "commits": heads,
            "cases": rows, "correct_decisions": {p: sum(row["decisions"][p] == row["expected"] for row in rows) for p in oracle["expected"]},
            "false_accepts": {p: sum(row["decisions"][p] and not row["expected"] for row in rows) for p in oracle["expected"]},
            "scope": "Six local Git fixtures, no external target execution or whole-environment claim"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, help="new directory to retain fixtures; omitted uses a temporary directory")
    args = parser.parse_args()
    if args.work:
        args.work.mkdir()
        result = compare(args.work.resolve())
    else:
        with tempfile.TemporaryDirectory() as temp:
            result = compare(Path(temp).resolve())
    print(encode(result).decode("utf-8"), end="")

if __name__ == "__main__":
    main()
