#!/usr/bin/env python3
"""Repeat fail-closed contract suites to expose order, temp-state, and flake defects."""
from __future__ import annotations

import argparse
import math
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
    ROOT / ".agents/skills/run-diverse-luna-research/scripts/test_dispatch_budget.py",
    ROOT / ".agents/skills/run-diverse-luna-project/scripts/test_dispatch_budget.py",
)
UNITTEST_COUNT = re.compile(r"Ran\s+(\d+)\s+tests?\b")


def parse_unittest_count(output: str) -> int:
    """Parse the observed unittest case count instead of using a stale constant."""
    match = UNITTEST_COUNT.search(output)
    if match is None:
        raise ValueError("unittest output did not contain an observed case count")
    return int(match.group(1))


def failure_detail(index, iterations, command, reason, stdout="", stderr="") -> str:
    def decode(value):
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
    tail = (decode(stdout) + "\n" + decode(stderr)).strip()[-2000:]
    return (f"iteration={index}/{iterations} command={subprocess.list2cmdline(command)}: "
            f"{reason}" + (f"\nOutput tail:\n{tail}" if tail else ""))


def run(iterations: int, command_timeout: float = 180.0) -> dict[str, float | int]:
    if iterations < 1 or iterations > 100:
        raise ValueError("iterations must be in the range 1..100")
    if not math.isfinite(command_timeout) or command_timeout <= 0:
        raise ValueError("command timeout must be a finite positive number of seconds")
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
            try:
                result = subprocess.run(
                    command, cwd=ROOT, env=environment, check=False,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", timeout=command_timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(failure_detail(index, iterations, command,
                    f"timed out after {command_timeout:g}s", exc.stdout, exc.stderr)) from exc
            if result.returncode:
                raise RuntimeError(failure_detail(index, iterations, command,
                    f"exit code {result.returncode}", result.stdout, result.stderr))
            try:
                observed_cases += parse_unittest_count(result.stdout + "\n" + result.stderr)
            except ValueError as exc:
                raise RuntimeError(failure_detail(index, iterations, command,
                    str(exc), result.stdout, result.stderr)) from exc
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--command-timeout", type=float, default=180.0,
                        help="Maximum seconds for each suite (default: 180).")
    args = parser.parse_args(argv)
    try:
        summary = run(args.iterations, args.command_timeout)
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS stress "
        f"iterations={summary['iterations']} cases={summary['cases']} "
        f"elapsed_seconds={summary['elapsed_seconds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
