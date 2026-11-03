"""Execute a fixed iequals task in a trusted checkout and record its code scope.

This imports the supplied source. It installs, downloads and patches nothing.
The scope is three package Python files, not an attested or complete environment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest
from unittest.mock import ANY

sys.dont_write_bytecode = True
MODULES = {
    "more_itertools": "more_itertools/__init__.py",
    "more_itertools.more": "more_itertools/more.py",
    "more_itertools.recipes": "more_itertools/recipes.py",
}
iequals = None

class TaskTests(unittest.TestCase):
    def test_fix_comparison_error(self):
        cause = ValueError("comparison failed")
        class Bad:
            def __eq__(self, other):
                raise cause
        with self.assertRaises(ValueError) as got:
            iequals([Bad()], [Bad()])
        self.assertIs(got.exception, cause)

    def test_fix_iteration_before_first(self):
        cause = ValueError("iteration start")
        def broken():
            raise cause
            yield
        with self.assertRaises(ValueError) as got:
            iequals(broken(), [])
        self.assertIs(got.exception, cause)

    def test_fix_iteration_after_prefix(self):
        cause = ValueError("iteration later")
        def broken():
            yield 1
            raise cause
        with self.assertRaises(ValueError) as got:
            iequals(broken(), [1])
        self.assertIs(got.exception, cause)

    def test_fix_comparison_truth_error(self):
        cause = ValueError("comparison truth")
        class BadTruth:
            def __bool__(self):
                raise cause
        class Item:
            def __eq__(self, other):
                return BadTruth()
        with self.assertRaises(ValueError) as got:
            iequals([Item()], [Item()])
        self.assertIs(got.exception, cause)

    def test_preserve_empty_and_single(self):
        self.assertTrue(iequals())
        self.assertTrue(iequals([], ()))
        self.assertTrue(iequals(iter([1, 2])))

    def test_preserve_equal_types(self):
        self.assertTrue(iequals([1, True], [1.0, 1+0j], iter([1, 1])))

    def test_preserve_unequal_values(self):
        self.assertFalse(iequals([1, 2], [1, 3]))

    def test_preserve_lengths(self):
        self.assertFalse(iequals([1], [1, 2]))
        self.assertFalse(iequals([1, 2], [1]))

    def test_preserve_order(self):
        self.assertFalse(iequals("abc", "acb"))

    def test_preserve_none_data(self):
        self.assertTrue(iequals([None, 1], (None, 1)))
        self.assertFalse(iequals([1], [1, None]))

    def test_preserve_unfakeable_fill(self):
        self.assertFalse(iequals([], [ANY]))
        self.assertFalse(iequals([ANY], []))

    def test_preserve_short_circuit(self):
        def later_error():
            yield 1
            raise RuntimeError("must not advance after mismatch")
        self.assertFalse(iequals(later_error(), [2, 3]))

class Results(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []
    def record(self, test, status, detail=None):
        row = {"id": test._testMethodName, "status": status}
        if detail is not None:
            row["detail"] = detail
        self.rows.append(row)
    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "PASS")
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "FAIL", self._exc_info_to_string(err, test))
    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "ERROR", self._exc_info_to_string(err, test))
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, "SKIP", reason)

def capture_scope(repo):
    package = repo / "more_itertools"
    paths = sorted(p.relative_to(repo).as_posix() for p in package.rglob("*.py"))
    if paths != sorted(MODULES.values()):
        raise RuntimeError("Package Python-file inventory differs from the reviewed scope")
    if any(package.rglob("*.pyc")) or any(package.rglob("*.pyo")):
        raise RuntimeError("Use a fresh source checkout without package bytecode caches")
    files, size = {}, 0
    for relative in paths:
        path = repo / relative
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise RuntimeError("Package source escapes the reviewed checkout")
        raw = path.read_bytes()
        files[relative] = hashlib.sha256(raw).hexdigest()
        size += len(raw)
    return files, size

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    before, size = capture_scope(repo)
    sys.path.insert(0, str(repo))
    import more_itertools
    origins = {}
    for name, relative in MODULES.items():
        module = sys.modules.get(name)
        if module is None or Path(module.__file__).resolve() != (repo / relative).resolve():
            raise RuntimeError("Imported module origin differs from the reviewed checkout")
        origins[name] = relative
    global iequals
    iequals = more_itertools.iequals
    result = Results()
    unittest.defaultTestLoader.loadTestsFromTestCase(TaskTests).run(result)
    after, after_size = capture_scope(repo)
    if before != after or size != after_size:
        raise RuntimeError("Package source changed during execution")
    report = {"schema_version": 1, "task": "more-itertools-1282",
              "primary_sha256": before["more_itertools/more.py"],
              "code_scope": before, "module_origins": origins,
              "runtime": {"python": platform.python_version(), "platform": sys.platform},
              "scope_capture": {"file_reads": 6, "bytes_read": size + after_size},
              "tests": result.rows}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() and not result.skipped else 1

if __name__ == "__main__":
    raise SystemExit(main())
