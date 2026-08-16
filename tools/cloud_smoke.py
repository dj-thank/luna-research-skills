#!/usr/bin/env python3
"""Run a deterministic, non-secret Codex Cloud readiness smoke test.

The public seams are ``repository_state``, ``http_probe``, ``run_command``, and
the CLI. Network mode sends only ordinary GET/HEAD traffic and one fixed POST
body (``codex_cloud_smoke=ok``); it never serializes repository or environment
contents.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
FIXED_POST_BODY = b"codex_cloud_smoke=ok"
NETWORK_PROBES = (
    ("GET", "https://learn.chatgpt.com/docs/cloud/internet-access", None),
    ("HEAD", "https://learn.chatgpt.com/docs/cloud/internet-access", None),
    ("GET", "https://github.com/dj-thank/luna-research-skills", None),
    ("HEAD", "https://github.com/dj-thank/luna-research-skills", None),
    ("POST", "https://httpbin.org/post", FIXED_POST_BODY),
)
MAX_OUTPUT_CHARS = 4000


def _tail(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-MAX_OUTPUT_CHARS:]


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def repository_state(root: Path, expected_head: str | None) -> dict[str, object]:
    """Return commit/branch/clean state; branch labels are not provenance."""
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current") or "DETACHED"
    status = _git(root, "status", "--porcelain=v1")
    expected_matches = expected_head is None or head == expected_head
    clean = not status
    return {
        "head": head,
        "expected_head": expected_head,
        "expected_head_matches": expected_matches,
        "branch": branch,
        "clean": clean,
        "status": status,
        "passed": expected_matches and clean,
    }


def http_probe(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    timeout: float = 20,
    opener: Callable[..., object] = urlopen,
) -> dict[str, object]:
    """Probe one URL while restricting outbound methods and POST bytes."""
    method = method.upper()
    if method not in {"GET", "HEAD", "POST"}:
        raise ValueError(f"unsupported smoke method: {method}")
    if method == "POST" and body != FIXED_POST_BODY:
        raise ValueError("POST body must be the fixed non-sensitive smoke payload")
    if method != "POST" and body is not None:
        raise ValueError("GET/HEAD probes cannot carry a request body")
    request = Request(url, data=body, method=method)
    request.add_header("User-Agent", "luna-cloud-smoke/2")
    if method == "POST":
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    started = time.monotonic()
    try:
        with opener(request, timeout=timeout) as response:
            if method != "HEAD":
                response.read(1)
            status = int(response.status)
            return {
                "method": method,
                "url": url,
                "status": status,
                "content_type": response.headers.get_content_type(),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "passed": 200 <= status < 400,
            }
    except HTTPError as exc:
        return {
            "method": method,
            "url": url,
            "status": exc.code,
            "content_type": exc.headers.get_content_type() if exc.headers else None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "passed": False,
            "error": f"HTTP {exc.code}",
        }
    except (OSError, URLError) as exc:
        return {
            "method": method,
            "url": url,
            "status": None,
            "content_type": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "passed": False,
            "error": type(exc).__name__,
        }


def run_command(
    command: list[str],
    root: Path,
    environment: dict[str, str],
    *,
    timeout: float,
) -> dict[str, object]:
    """Run one bounded validation command and normalize its receipt."""
    started = time.monotonic()
    shown = shlex.join(command)
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": shown,
            "status": "timed_out",
            "exit_code": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": _tail(exc.stdout),
            "stderr_tail": _tail(exc.stderr),
        }
    return {
        "command": shown,
        "status": "passed" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": _tail(result.stdout),
        "stderr_tail": _tail(result.stderr),
    }


def _commands(root: Path, temporary: Path, iterations: int) -> list[tuple[list[str], float]]:
    release_output = temporary / "release"
    return [
        ([sys.executable, "tools/validate_repository.py"], 120),
        ([sys.executable, "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"], 180),
        ([sys.executable, ".agents/skills/run-diverse-luna-research/scripts/test_check_setup.py"], 180),
        ([sys.executable, ".agents/skills/run-diverse-luna-project/scripts/test_check_setup.py"], 180),
        ([sys.executable, "tools/stress_contracts.py", "--iterations", str(iterations)], 1200),
        ([sys.executable, "-m", "compileall", "-q", ".agents", "tools"], 180),
        ([sys.executable, "tools/build_release.py", "--root", str(root), "--output", str(release_output)], 180),
        (["git", "diff", "--check"], 60),
        (["git", "fsck", "--no-progress"], 180),
    ]


def run_smoke(root: Path, expected_head: str | None, network: bool, iterations: int) -> dict[str, object]:
    if iterations < 1 or iterations > 100:
        raise ValueError("iterations must be in the range 1..100")
    if not expected_head:
        raise ValueError("--expected-head is required for a provenance-bound smoke run")
    before = repository_state(root, expected_head)
    environment_receipt = {
        "PYTHONUTF8_is_1": os.environ.get("PYTHONUTF8") == "1",
        "PYTHONDONTWRITEBYTECODE_is_1": os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
    }
    if not bool(before["passed"]) or not all(environment_receipt.values()):
        return {
            "schema_version": 1,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "verdict": "FAIL",
            "gate_ceiling": "LOCAL_PASS",
            "repository_before": before,
            "environment": environment_receipt,
            "network_enabled_for_smoke": network,
            "network": [],
            "commands": [],
            "powershell": {
                "status": "not_run",
                "reason": "repository or environment precondition failed",
            },
            "repository_after": repository_state(root, expected_head),
        }
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="luna-cloud-smoke-") as temporary_name:
        temporary = Path(temporary_name)
        environment["PYTHONPYCACHEPREFIX"] = str(temporary / "pycache")
        command_results = [
            run_command(command, root, environment, timeout=timeout)
            for command, timeout in _commands(root, temporary, iterations)
        ]
        pwsh = shutil.which("pwsh")
        if pwsh:
            command_results.append(
                run_command(
                    [pwsh, "-NoProfile", "-File", "tools/Test-LunaMigrationTools.ps1", "-Source", ".agents/skills"],
                    root,
                    environment,
                    timeout=600,
                )
            )
            powershell_status: dict[str, object] = {"status": command_results[-1]["status"], "executable": "pwsh"}
        else:
            powershell_status = {
                "status": "not_run",
                "reason": "pwsh unavailable; Windows PowerShell and pwsh remain CI matrix gates",
            }
    network_results = [
        http_probe(method, url, body=body) for method, url, body in NETWORK_PROBES
    ] if network else []
    after = repository_state(root, expected_head)
    passed = (
        bool(before["passed"])
        and bool(after["passed"])
        and all(result["status"] == "passed" for result in command_results)
        and all(bool(result["passed"]) for result in network_results)
        and all(environment_receipt.values())
    )
    return {
        "schema_version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "LOCAL_PASS" if passed else "FAIL",
        "gate_ceiling": "LOCAL_PASS",
        "repository_before": before,
        "environment": environment_receipt,
        "network_enabled_for_smoke": network,
        "network": network_results,
        "commands": command_results,
        "powershell": powershell_status,
        "repository_after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--network", action="store_true")
    parser.add_argument("--iterations", type=int, default=25)
    args = parser.parse_args()
    try:
        report = run_smoke(args.root.resolve(), args.expected_head, args.network, args.iterations)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        report = {
            "schema_version": 1,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "verdict": "FAIL",
            "gate_ceiling": "LOCAL_PASS",
            "error": f"{type(exc).__name__}: {exc}",
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "LOCAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
