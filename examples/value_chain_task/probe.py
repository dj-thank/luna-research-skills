"""Run a fixed external value_chain task against an explicit, trusted checkout.

This imports and executes that checkout. It never downloads, installs or patches it.
Results describe this process and source bytes, not independent agent performance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest
from itertools import count, islice

sys.dont_write_bytecode = True
value_chain = None

class TaskTests(unittest.TestCase):
    def test_fix_map_error(self):
        stream = value_chain(map(len, ["ab", "cde", 5]))
        self.assertEqual([next(stream), next(stream)], [2, 3])
        with self.assertRaises(TypeError):
            next(stream)

    def test_fix_generator_before_first(self):
        cause = TypeError("before first")
        def broken():
            raise cause
            yield
        with self.assertRaises(TypeError) as got:
            next(value_chain(broken()))
        self.assertIs(got.exception, cause)

    def test_fix_generator_after_prefix(self):
        cause = TypeError("after prefix")
        later = []
        def broken():
            yield "prefix"
            raise cause
        def untouched():
            later.append(True)
            yield "later"
        stream = value_chain(broken(), untouched())
        self.assertEqual(next(stream), "prefix")
        with self.assertRaises(TypeError) as got:
            next(stream)
        self.assertIs(got.exception, cause)
        self.assertEqual(later, [])

    def test_fix_iterator_next(self):
        cause = TypeError("iterator next")
        class Broken:
            def __iter__(self):
                return self
            def __next__(self):
                raise cause
        with self.assertRaises(TypeError) as got:
            next(value_chain(Broken()))
        self.assertIs(got.exception, cause)

    def test_preserve_empty(self):
        self.assertEqual(list(value_chain()), [])
        self.assertEqual(list(value_chain([], ())), [])

    def test_preserve_scalars(self):
        marker = object()
        values = [None, False, 0, 2.5, marker]
        self.assertEqual(list(value_chain(*values)), values)

    def test_preserve_text_and_bytes(self):
        values = ["ab", b"cd", "", b""]
        self.assertEqual(list(value_chain(*values)), values)

    def test_preserve_one_level(self):
        self.assertEqual(list(value_chain([1, [2, [3]]], (4, (5,)))), [1, [2, [3]], 4, (5,)])

    def test_preserve_mapping(self):
        self.assertEqual(list(value_chain({"first": 1, "second": 2})), ["first", "second"])

    def test_preserve_iter_type_error(self):
        class Scalar:
            def __iter__(self):
                raise TypeError("classification failure")
        marker = Scalar()
        actual = list(value_chain(marker))
        self.assertEqual(len(actual), 1)
        self.assertIs(actual[0], marker)

    def test_preserve_laziness(self):
        touched = []
        def numbers():
            touched.append(True)
            yield from count()
        stream = value_chain(numbers())
        self.assertEqual(touched, [])
        self.assertEqual(list(islice(stream, 3)), [0, 1, 2])
        self.assertEqual(touched, [True])

    def test_preserve_other_error(self):
        cause = ValueError("other error")
        def broken():
            raise cause
            yield
        with self.assertRaises(ValueError) as got:
            next(value_chain(broken()))
        self.assertIs(got.exception, cause)

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

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    source = repo / "more_itertools/more.py"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    sys.path.insert(0, str(repo))
    import more_itertools
    import more_itertools.more as module
    if Path(module.__file__).resolve() != source.resolve():
        raise RuntimeError("Imported source is not the requested checkout")
    global value_chain
    value_chain = more_itertools.value_chain
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TaskTests)
    result = Results()
    suite.run(result)
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError("Source changed during execution")
    report = {"schema_version": 1, "task": "more-itertools-1250",
              "source_sha256": before, "python": platform.python_version(),
              "platform": sys.platform, "tests": result.rows}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() and not result.skipped else 1

if __name__ == "__main__":
    raise SystemExit(main())
