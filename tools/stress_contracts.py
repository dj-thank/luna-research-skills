#!/usr/bin/env python3
"""Repeat fail-closed contract suites to expose order, temp-state, and flake defects."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
CHECKER_TESTS = (
    ROOT / ".agents/skills/run-diverse-luna-research/scripts/test_check_setup.py",
    ROOT / ".agents/skills/run-diverse-luna-project/scripts/test_check_setup.py",
)
UNITTEST_COUNT = re.compile(r"Ran\s+(\d+)\s+tests?\b")


def parse_unittest_count(output: str) -> int:
    """Parse the observed unittest case count instead of using a stale constant."""
    match = UNITTEST_COUNT.search(output)
    if match is None:
        raise ValueError("unittest output did not contain an observed case count")
    return int(match.group(1))


def run(iterations: int) -> dict[str, float | int]:
    if iterations < 1 or iterations > 100:
        raise ValueError("iterations must be in the range 1..100")
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    cases_per_iteration: int | None = None
    for index in range(1, iterations + 1):
        commands = [
            [sys.executable, "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"],
            *[[sys.executable, str(test)] for test in CHECKER_TESTS],
        ]
        observed_cases = 0
        for command in commands:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            observed_cases += parse_unittest_count(result.stdout + "\n" + result.stderr)
        if cases_per_iteration is None:
            cases_per_iteration = observed_cases
        elif observed_cases != cases_per_iteration:
            raise RuntimeError(
                "unittest case count drifted between iterations: "
                f"expected {cases_per_iteration}, observed {observed_cases}"
            )
        print(f"PASS iteration={index}/{iterations}", flush=True)
    elapsed = time.monotonic() - started
    if cases_per_iteration is None:
        raise RuntimeError("no unittest cases were observed")
    return {
        "iterations": iterations,
        "cases_per_iteration": cases_per_iteration,
        "cases": iterations * cases_per_iteration,
        "elapsed_seconds": round(elapsed, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=25)
    args = parser.parse_args()
    summary = run(args.iterations)
    print(
        "PASS stress "
        f"iterations={summary['iterations']} cases={summary['cases']} "
        f"elapsed_seconds={summary['elapsed_seconds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
