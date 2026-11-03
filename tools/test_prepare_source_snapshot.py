"""Exercise actual local Git preparation and failure boundaries."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import example_canonical_source as X
import prepare_source_snapshot as S
from read_evidence import encode

class CanonicalSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        cls.oracle = json.loads(X.ORACLE.read_bytes())
        cls.repo, cls.heads, cls.gold = X.fixture(cls.root, cls.oracle)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def paths(self, suffix=""):
        stem = self._testMethodName + suffix
        return self.root / (stem + ".json"), self.root / (stem + "-out")

    def request(self, suffix="", data=None):
        path, target = self.paths(suffix)
        data = data if data is not None else X.manifest(self.heads["fixed"], self.oracle)
        path.write_bytes(encode(data))
        return path, X.digest(path.read_bytes()), target

    def test_preregistered_configuration_comparison(self):
        folder = self.root / "comparison"; folder.mkdir()
        result = X.compare(folder)
        self.assertEqual(result["correct_decisions"], {"checkout": 4, "canonical": 6, "normalize": 3})
        self.assertEqual(result["false_accepts"], {"checkout": 0, "canonical": 0, "normalize": 0})
        stored = json.loads((X.ORACLE.parents[2] / "examples/canonical_source/results.json").read_bytes())
        self.assertEqual(result, stored["comparison"])

    def test_saved_result_pins_and_literal_oracle(self):
        repo = X.ORACLE.parents[2]
        record = json.loads((repo / "examples/canonical_source/results.json").read_bytes())
        self.assertEqual(record["oracle_sha256"], X.digest(X.ORACLE.read_bytes()))
        for name, expected in record["implementation_sha256"].items():
            self.assertEqual(X.digest((repo / "tools" / name).read_bytes()), expected, name)
        self.assertEqual(record["comparison"]["oracle_sha256"], record["oracle_sha256"])
        self.assertEqual(bytes.fromhex(self.oracle["files"]["data/mixed.raw"]["hex"]), b"\x00a\r\nb\rc\n\xff")
        self.assertFalse(record["candidate_refinement"]["oracle_changed"])
        self.assertTrue(record["candidate_refinement"]["full_comparison_equal"])

    def test_plan_and_export_preserve_raw_bytes_and_source(self):
        path, pin, target = self.request()
        before = {n: (self.repo / n).read_bytes() for n in self.gold}
        config = (self.repo / ".git/config").read_bytes()
        plan = S.prepare(self.repo, path, pin, target)
        self.assertEqual(plan["status"], "PLAN"); self.assertFalse(target.exists())
        result = S.prepare(self.repo, path, pin, target, apply=True)
        self.assertEqual(result["status"], "EXPORTED")
        self.assertEqual({n: (target / n).read_bytes() for n in self.gold}, self.gold)
        self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}, set(self.gold))
        self.assertEqual({n: (self.repo / n).read_bytes() for n in self.gold}, before)
        self.assertEqual((self.repo / ".git/config").read_bytes(), config)
        self.assertEqual((target / "data/mixed.raw").read_bytes(), b"\x00a\r\nb\rc\n\xff")

    def test_pins_duplicate_json_and_nonregular_manifest(self):
        path, pin, target = self.request()
        result = S.prepare(self.repo, path, "0" * 64, target, apply=True)
        self.assertEqual(result["status"], "REFUSED"); self.assertFalse(target.exists())
        path.write_bytes(b'{"schema_version":1,"schema_version":1}')
        result = S.prepare(self.repo, path, X.digest(path.read_bytes()), target, apply=True)
        self.assertEqual(result["status"], "REFUSED")
        result = S.prepare(self.repo, self.root, pin, target, apply=True)
        self.assertEqual(result["status"], "REFUSED"); self.assertFalse(target.exists())
        if hasattr(os, "mkfifo"):
            fifo = self.root / "manifest-fifo"; os.mkfifo(fifo)
            result = S.prepare(self.repo, fifo, pin, target, apply=True)
            self.assertEqual(result["status"], "REFUSED")

    def test_size_digest_and_same_size_semantic_mutation(self):
        for index, field in enumerate(("bytes", "sha256")):
            data = X.manifest(self.heads["fixed"], self.oracle)
            row = next(r for r in data["files"] if r["path"] == "src/task.py")
            row[field] = row[field] + 1 if field == "bytes" else "0" * 64
            path, pin, target = self.request(str(index), data)
            self.assertEqual(S.prepare(self.repo, path, pin, target, apply=True)["status"], "REFUSED")
            self.assertFalse(target.exists())
        (self.repo / "src/task.py").write_bytes(b"RESULT = 9\n")
        X.git(self.repo, "add", "."); X.git(self.repo, "commit", "-qm", "same-size mutation")
        bad = X.git(self.repo, "rev-parse", "HEAD").decode().strip()
        path, pin, target = self.request("same", X.manifest(bad, self.oracle))
        result = S.prepare(self.repo, path, pin, target, apply=True)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("content differs", result["error"]); self.assertFalse(target.exists())

    def test_existing_targets_and_source_overlap_are_untouched(self):
        path, pin, target = self.request()
        target.mkdir(); (target / "keep").write_bytes(b"user-owned")
        self.assertEqual(S.prepare(self.repo, path, pin, target, apply=True)["status"], "REFUSED")
        self.assertEqual((target / "keep").read_bytes(), b"user-owned")
        for dest in (self.repo / "new-output", self.repo / ".git/new-output", self.root / "missing-parent/out"):
            self.assertEqual(S.prepare(self.repo, path, pin, dest, apply=True)["status"], "REFUSED")
            self.assertFalse(dest.exists())

    def test_symlink_and_gitlink_tree_modes_are_refused(self):
        for mode, kind in (("120000", "blob"), ("160000", "commit")):
            oid = X.git(self.repo, "hash-object", "-w", "--stdin", input=b"xx").decode().strip() if kind == "blob" else self.heads["fixed"]
            tree = X.git(self.repo, "mktree", input=(mode + " " + kind + " " + oid + "\tentry\n").encode()).decode().strip()
            commit = X.git(self.repo, "commit-tree", tree, "-m", "indirect").decode().strip()
            data = {"schema_version": 1, "commit": commit, "files": [{"path": "entry", "bytes": 2, "sha256": X.digest(b"xx"), "mode": "100644"}]}
            path, pin, target = self.request(mode, data)
            self.assertEqual(S.prepare(self.repo, path, pin, target, apply=True)["status"], "REFUSED")
            self.assertFalse(target.exists())

    def test_replacement_refs_and_git_environment_do_not_redirect_reads(self):
        X.git(self.repo, "replace", self.heads["fixed"], self.heads["changed"])
        try:
            path, pin, target = self.request()
            with mock.patch.dict(os.environ, {"GIT_DIR": str(self.root / "nonexistent"), "GIT_WORK_TREE": str(self.root)}):
                result = S.prepare(self.repo, path, pin, target, apply=True)
            self.assertEqual(result["status"], "EXPORTED")
            self.assertEqual((target / "src/task.py").read_bytes(), b"RESULT = 2\n")
        finally:
            X.git(self.repo, "replace", "-d", self.heads["fixed"])

    def test_manifest_paths_types_and_budgets(self):
        base = X.manifest(self.heads["fixed"], self.oracle)
        bad_paths = ("../escape", "/absolute", "C:/escape", "a\\b", "a//b", ".git/config", "AUX.txt", "a./b", ".", "src/../x")
        for value in bad_paths:
            data = copy.deepcopy(base); data["files"][0]["path"] = value
            with self.assertRaises(ValueError): S.validate(data)
        for kind in ("case", "parent_case", "overlap", "mode", "bool", "file_limit", "count", "total", "commit", "schema"):
            data = copy.deepcopy(base)
            if kind == "case": data["files"].append(dict(data["files"][0], path=data["files"][0]["path"].upper()))
            elif kind == "parent_case": data["files"].append(dict(data["files"][0], path="SRC/other.py"))
            elif kind == "overlap": data["files"].append(dict(data["files"][0], path="src"))
            elif kind == "mode": data["files"][0]["mode"] = "120000"
            elif kind == "bool": data["files"][0]["bytes"] = True
            elif kind == "file_limit": data["files"][0]["bytes"] = S.MAX_FILE_BYTES + 1
            elif kind == "count": data["files"] = data["files"] * 65
            elif kind == "total": data["files"] = [dict(data["files"][0], path=f"file{i}", bytes=S.MAX_FILE_BYTES) for i in range(9)]
            elif kind == "commit": data["commit"] = "HEAD"
            else: data["schema_version"] = True
            with self.assertRaises(ValueError): S.validate(data)

    def test_partial_write_is_preserved_and_never_marked_exported(self):
        path, pin, target = self.request()
        original = Path.open
        def fail(path, mode="r", *args, **kwargs):
            if path == target / "src/task.py" and mode == "xb":
                raise OSError("injected write failure")
            return original(path, mode, *args, **kwargs)
        with mock.patch.object(Path, "open", fail):
            result = S.prepare(self.repo, path, pin, target, apply=True)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertTrue(result["target_created"])
        self.assertEqual(result["completed_files"], [".gitattributes", "data/mixed.raw"])
        self.assertEqual((target / "data/mixed.raw").read_bytes(), self.gold["data/mixed.raw"])
        self.assertFalse((target / "src/task.py").exists())
        self.assertEqual(S.prepare(self.repo, path, pin, target, apply=True)["status"], "REFUSED")
        self.assertTrue(target.exists())

    def test_cli_dry_run_and_apply(self):
        path, pin, target = self.request()
        command = [sys.executable, str(Path(S.__file__)), "--repo", str(self.repo), "--manifest", str(path), "--sha256", pin, "--target", str(target)]
        for extra, status in (([], "PLAN"), (["--apply"], "EXPORTED")):
            result = subprocess.run(command + extra, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], status)
            self.assertEqual(target.exists(), bool(extra))

    def test_executable_mode_is_pinned(self):
        oid = X.git(self.repo, "hash-object", "-w", "--stdin", input=b"pass\n").decode().strip()
        tree = X.git(self.repo, "mktree", input=("100755 blob " + oid + "\tscript.py\n").encode()).decode().strip()
        commit = X.git(self.repo, "commit-tree", tree, "-m", "executable").decode().strip()
        data = {"schema_version": 1, "commit": commit, "files": [{"path": "script.py", "mode": "100755", "sha256": X.digest(b"pass\n"), "bytes": 5}]}
        path, pin, target = self.request(data=data)
        result = S.prepare(self.repo, path, pin, target, apply=True)
        self.assertEqual(result["status"], "EXPORTED"); self.assertEqual(result["files"][0]["mode"], "100755")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((target / "script.py").stat().st_mode), 0o755)

if __name__ == "__main__":
    unittest.main()
