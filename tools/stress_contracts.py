#!/usr/bin/env python3
"""Repeat fail-closed contract suites to expose order, temp-state, and flake defects."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
CHECKER_TESTS = (
    ROOT / ".agents/skills/run-diverse-luna-research/scripts/test_check_setup.py",
    ROOT / ".agents/skills/run-diverse-luna-project/scripts/test_check_setup.py",
)
CASES_PER_ITERATION = 169  # 75 + 75 checker cases and 19 repository/tool cases.


def run(iterations: int) -> dict[str, float | int]:
    if iterations < 1 or iterations > 100:
        raise ValueError("iterations must be in the range 1..100")
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    for index in range(1, iterations + 1):
        commands = [
            [sys.executable, "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"],
            *[[sys.executable, str(test)] for test in CHECKER_TESTS],
        ]
        for command in commands:
            subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        print(f"PASS iteration={index}/{iterations}", flush=True)
    elapsed = time.monotonic() - started
    return {
        "iterations": iterations,
        "cases": iterations * CASES_PER_ITERATION,
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
