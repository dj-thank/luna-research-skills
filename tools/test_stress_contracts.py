import contextlib
import io
import subprocess
import unittest
from unittest import mock

import stress_contracts as stress


class StressContractTests(unittest.TestCase):
    def test_counts_observed_cases_and_applies_timeout_to_every_suite(self):
        result = subprocess.CompletedProcess([], 0, "", "Ran 4 tests in 0.1s\nOK\n")
        with mock.patch.object(stress.subprocess, "run", return_value=result) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                summary = stress.run(2, command_timeout=0.5)
        self.assertEqual(summary["cases"], 40)
        self.assertEqual(run.call_count, 10)
        self.assertTrue(all(call.kwargs["timeout"] == 0.5 for call in run.call_args_list))

    def test_timeout_reports_iteration_suite_and_partial_output(self):
        error = subprocess.TimeoutExpired("suite", 0.5, output=b"partial", stderr=b"waiting")
        with mock.patch.object(stress.subprocess, "run", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                stress.run(2, 0.5)
        message = str(raised.exception)
        for expected in ("iteration=1/2", "unittest discover", "timed out after 0.5s", "partial", "waiting"):
            self.assertIn(expected, message)

    def test_failure_tail_is_bounded_and_cli_has_no_traceback(self):
        result = subprocess.CompletedProcess([], 7, "x" * 4000, "decisive failure")
        output = io.StringIO()
        with mock.patch.object(stress.subprocess, "run", return_value=result):
            with contextlib.redirect_stderr(output):
                code = stress.main(["--iterations", "2"])
        self.assertEqual(code, 1)
        self.assertIn("exit code 7", output.getvalue())
        self.assertIn("decisive failure", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())
        self.assertLess(len(output.getvalue()), 2500)

    def test_invalid_timeouts_do_not_launch_commands(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), mock.patch.object(stress.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    stress.run(1, value)
                run.assert_not_called()

    def test_missing_count_names_the_failing_command(self):
        result = subprocess.CompletedProcess([], 0, "no cases", "")
        with mock.patch.object(stress.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "iteration=1/1.*unittest discover"):
                stress.run(1)

    def test_case_count_drift_remains_an_error(self):
        first = subprocess.CompletedProcess([], 0, "Ran 4 tests", "")
        changed = subprocess.CompletedProcess([], 0, "Ran 5 tests", "")
        with mock.patch.object(stress.subprocess, "run", side_effect=[first] * 5 + [changed] * 5):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "count drifted"):
                stress.run(2)
