from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import cloud_smoke
import stress_contracts


class _ProbeHandler(BaseHTTPRequestHandler):
    posted_body = b""

    def _respond(self, include_body: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        if include_body:
            self.wfile.write(b"ok")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        self._respond(True)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler contract
        self._respond(False)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        length = int(self.headers.get("Content-Length", "0"))
        type(self).posted_body = self.rfile.read(length)
        self._respond(True)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class CloudSmokeTests(unittest.TestCase):
    def _git_repo(self) -> tuple[Path, str]:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        subprocess.run(["git", "init", "-b", "work"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Cloud Smoke Test"], cwd=root, check=True)
        (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        return root, head

    def test_matching_head_accepts_temporary_work_branch(self) -> None:
        root, head = self._git_repo()
        state = cloud_smoke.repository_state(root, head)
        self.assertEqual(state["branch"], "work")
        self.assertTrue(state["expected_head_matches"])
        self.assertTrue(state["clean"])
        self.assertTrue(state["passed"])

    def test_dirty_tree_fails_even_when_head_matches(self) -> None:
        root, head = self._git_repo()
        (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
        state = cloud_smoke.repository_state(root, head)
        self.assertTrue(state["expected_head_matches"])
        self.assertFalse(state["clean"])
        self.assertFalse(state["passed"])

    def test_http_probes_support_get_head_and_fixed_post_only(self) -> None:
        _ProbeHandler.posted_body = b""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}/probe"
            get_result = cloud_smoke.http_probe("GET", endpoint)
            head_result = cloud_smoke.http_probe("HEAD", endpoint)
            post_result = cloud_smoke.http_probe(
                "POST", endpoint, body=cloud_smoke.FIXED_POST_BODY
            )
            self.assertTrue(get_result["passed"])
            self.assertTrue(head_result["passed"])
            self.assertTrue(post_result["passed"])
            self.assertEqual(_ProbeHandler.posted_body, b"codex_cloud_smoke=ok")
            with self.assertRaises(ValueError):
                cloud_smoke.http_probe("PUT", endpoint)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_command_result_distinguishes_success_failure_and_timeout(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        environment = os.environ.copy()
        success = cloud_smoke.run_command(
            [sys.executable, "-c", "print('ok')"], root, environment, timeout=2
        )
        failure = cloud_smoke.run_command(
            [sys.executable, "-c", "raise SystemExit(7)"], root, environment, timeout=2
        )
        timed_out = cloud_smoke.run_command(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            root,
            environment,
            timeout=0.05,
        )
        self.assertEqual(success["status"], "passed")
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["exit_code"], 7)
        self.assertEqual(timed_out["status"], "timed_out")

    def test_unittest_case_count_is_parsed_from_observed_output(self) -> None:
        output = "........\nRan 26 tests in 0.123s\n\nOK\n"
        self.assertEqual(stress_contracts.parse_unittest_count(output), 26)
        with self.assertRaises(ValueError):
            stress_contracts.parse_unittest_count("OK without a count")

    def test_run_smoke_requires_an_exact_expected_head(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected-head"):
            cloud_smoke.run_smoke(Path("."), None, False, 1)

    def test_dirty_precondition_stops_before_commands_or_network(self) -> None:
        root, head = self._git_repo()
        (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
        environment = {
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(
                cloud_smoke,
                "_commands",
                side_effect=AssertionError("commands must not start after failed provenance"),
            ),
            patch.object(
                cloud_smoke,
                "http_probe",
                side_effect=AssertionError("network must not start after failed provenance"),
            ),
        ):
            report = cloud_smoke.run_smoke(root, head, True, 1)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["commands"], [])
        self.assertEqual(report["network"], [])
        self.assertEqual(report["powershell"]["status"], "not_run")


if __name__ == "__main__":
    unittest.main()
