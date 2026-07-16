from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "luna-research-skills"
CONFIGURE = (
    PLUGIN
    / "skills"
    / "configure-luna-subagents"
    / "scripts"
    / "configure_luna.py"
)
CHECK = (
    PLUGIN
    / "skills"
    / "run-diverse-luna-research"
    / "scripts"
    / "check_setup.py"
)


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def install_valid_home(home: Path) -> None:
    result = run_script(CONFIGURE, "install", "--apply", "--codex-home", str(home))
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def write_rollout(home: Path, thread_id: str, model: str = "gpt-5.6-luna") -> Path:
    path = home / "sessions" / "2026" / "07" / "17" / f"rollout-test-{thread_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "type": "session_meta",
            "payload": {"id": thread_id, "thread_source": "subagent"},
        },
        {
            "type": "turn_context",
            "payload": {"model": model, "effort": "medium"},
        },
    ]
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    return path


class CheckSetupTests(unittest.TestCase):
    def test_static_preflight_passes_for_managed_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            workspace.mkdir()
            install_valid_home(home)
            result = run_script(
                CHECK, "--codex-home", str(home), "--workspace", str(workspace)
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("static Luna ordinary-agent routing", result.stdout)
            self.assertIn("--runtime-thread", result.stdout)

    def test_wrong_model_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            workspace.mkdir()
            install_valid_home(home)
            role_path = home / "agents" / "default.toml"
            role = role_path.read_text(encoding="utf-8").replace(
                'model = "gpt-5.6-luna"', 'model = "gpt-5.6-sol"'
            )
            role_path.write_text(role, encoding="utf-8")
            result = run_script(
                CHECK, "--codex-home", str(home), "--workspace", str(workspace)
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("model must be 'gpt-5.6-luna'", result.stdout)

    def test_workspace_default_override_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            override = workspace / ".codex" / "agents" / "default.toml"
            override.parent.mkdir(parents=True)
            override.write_text(
                'name = "default"\nmodel = "other"\nmodel_reasoning_effort = "medium"\n'
                'developer_instructions = "bounded"\n',
                encoding="utf-8",
            )
            install_valid_home(home)
            result = run_script(
                CHECK, "--codex-home", str(home), "--workspace", str(workspace)
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("model must be 'gpt-5.6-luna'", result.stdout)

    def test_spawn_schema_requires_fork_turns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            workspace.mkdir()
            install_valid_home(home)
            schema_path = root / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "name": "collaboration.spawn_agent",
                        "parameters": {
                            "properties": {"message": {"type": "string"}}
                        },
                    }
                ),
                encoding="utf-8",
            )
            failed = run_script(
                CHECK,
                "--codex-home",
                str(home),
                "--workspace",
                str(workspace),
                "--spawn-schema-json",
                str(schema_path),
            )
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
            self.assertIn("does not expose fork_turns", failed.stdout)

            schema_path.write_text(
                json.dumps(
                    {
                        "name": "collaboration.spawn_agent",
                        "parameters": {
                            "properties": {
                                "message": {"type": "string"},
                                "task_name": {"type": "string"},
                                "fork_turns": {"type": "string"},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            passed = run_script(
                CHECK,
                "--codex-home",
                str(home),
                "--workspace",
                str(workspace),
                "--spawn-schema-json",
                str(schema_path),
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)

    def test_runtime_thread_lookup_and_model_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            workspace.mkdir()
            install_valid_home(home)
            thread_id = str(uuid.uuid4())
            write_rollout(home, thread_id)
            passed = run_script(
                CHECK,
                "--codex-home",
                str(home),
                "--workspace",
                str(workspace),
                "--runtime-thread",
                thread_id,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("VERIFIED", passed.stdout)

            wrong_thread = str(uuid.uuid4())
            write_rollout(home, wrong_thread, model="gpt-5.6-sol")
            failed = run_script(
                CHECK,
                "--codex-home",
                str(home),
                "--workspace",
                str(workspace),
                "--runtime-thread",
                wrong_thread,
            )
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
            self.assertIn("runtime model must be 'gpt-5.6-luna'", failed.stdout)

    def test_runtime_thread_rejects_non_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            workspace.mkdir()
            install_valid_home(home)
            result = run_script(
                CHECK,
                "--codex-home",
                str(home),
                "--workspace",
                str(workspace),
                "--runtime-thread",
                "../../not-a-thread",
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("must be a UUID", result.stdout)


if __name__ == "__main__":
    unittest.main()
