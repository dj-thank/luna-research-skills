from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "plugins"
    / "luna-research-skills"
    / "skills"
    / "configure-luna-subagents"
    / "scripts"
    / "configure_luna.py"
)


def run_cli(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--codex-home", str(home)],
        text=True,
        capture_output=True,
        check=False,
    )


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ConfigureLunaTests(unittest.TestCase):
    def test_plan_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = run_cli(home, "plan")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PLAN ONLY", result.stdout)
            self.assertFalse((home / "config.toml").exists())

    def test_clean_install_status_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installed = run_cli(home, "install", "--apply")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            with (home / "config.toml").open("rb") as handle:
                agents = tomllib.load(handle)["agents"]
            self.assertIs(agents["enabled"], True)
            self.assertEqual(agents["max_concurrent_threads_per_session"], 40)
            self.assertEqual(agents["default_subagent_model"], "gpt-5.6-luna")
            self.assertEqual(agents["default_subagent_reasoning_effort"], "medium")
            self.assertFalse((home / "agents" / "default.toml").exists())

            status = run_cli(home, "status")
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("managed v2 installation is intact", status.stdout)

            restored = run_cli(home, "uninstall", "--apply")
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            self.assertFalse((home / "config.toml").exists())
            self.assertFalse((home / ".luna-research-skills-state.json").exists())

    def test_conflicts_require_flag_and_restore_exact_original(self) -> None:
        original = (
            b'title = "preserve me"\r\n\r\n'
            b"[agents]\r\nenabled = false\r\n"
            b"max_concurrent_threads_per_session = 8\r\n"
            b'default_subagent_model = "another-model"\r\n'
            b'default_subagent_reasoning_effort = "high"\r\n\r\n'
            b"[unrelated]\r\nvalue = 17\r\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "config.toml").write_bytes(original)
            blocked = run_cli(home, "install", "--apply")
            self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
            self.assertIn("--replace-settings", blocked.stdout)
            self.assertEqual((home / "config.toml").read_bytes(), original)

            installed = run_cli(home, "install", "--apply", "--replace-settings")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            patched = (home / "config.toml").read_text(encoding="utf-8")
            self.assertIn('title = "preserve me"', patched)
            self.assertIn("[unrelated]", patched)
            self.assertIn("value = 17", patched)

            restored = run_cli(home, "uninstall", "--apply")
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            self.assertEqual((home / "config.toml").read_bytes(), original)

    def test_legacy_v1_migration_restores_role_and_installs_native_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            backup = home / "backups" / "luna-research-skills" / "legacy"
            backup.mkdir(parents=True)
            original_config = b'title = "before-v1"\n'
            original_role = b'name = "default"\nmodel = "original"\n'
            installed_config = b"[features]\nmulti_agent = true\n[agents]\nmax_threads = 40\nmax_depth = 2\n"
            installed_role = b'name = "default"\nmodel = "gpt-5.6-luna"\nmodel_reasoning_effort = "medium"\ndeveloper_instructions = "managed"\n'
            (backup / "config.toml").write_bytes(original_config)
            (backup / "agents-default.toml").write_bytes(original_role)
            (home / "agents").mkdir(parents=True)
            (home / "config.toml").write_bytes(installed_config)
            (home / "agents" / "default.toml").write_bytes(installed_role)
            state = {
                "version": 1,
                "files": {
                    "config.toml": {
                        "existed": True,
                        "original_sha256": digest(original_config),
                        "installed_sha256": digest(installed_config),
                        "backup": "backups/luna-research-skills/legacy/config.toml",
                    },
                    "agents/default.toml": {
                        "existed": True,
                        "original_sha256": digest(original_role),
                        "installed_sha256": digest(installed_role),
                        "backup": "backups/luna-research-skills/legacy/agents-default.toml",
                    },
                },
            }
            (home / ".luna-research-skills-state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )

            migrated = run_cli(home, "migrate", "--apply")
            self.assertEqual(migrated.returncode, 0, migrated.stdout + migrated.stderr)
            self.assertIn("MIGRATED", migrated.stdout)
            self.assertEqual((home / "agents" / "default.toml").read_bytes(), original_role)
            with (home / "config.toml").open("rb") as handle:
                config = tomllib.load(handle)
            self.assertEqual(config["title"], "before-v1")
            self.assertEqual(config["agents"]["default_subagent_model"], "gpt-5.6-luna")
            new_state = json.loads(
                (home / ".luna-research-skills-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(new_state["version"], 2)
            self.assertEqual(set(new_state["files"]), {"config.toml"})

    def test_drift_blocks_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual(run_cli(home, "install", "--apply").returncode, 0)
            config_path = home / "config.toml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8") + "# user edit\n",
                encoding="utf-8",
            )
            blocked = run_cli(home, "uninstall", "--apply")
            self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
            self.assertIn("changed after installation", blocked.stdout)
            self.assertTrue(config_path.read_text(encoding="utf-8").endswith("# user edit\n"))

    def test_malformed_config_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            malformed = b"[agents\nenabled = true\n"
            (home / "config.toml").write_bytes(malformed)
            result = run_cli(home, "install", "--apply", "--replace-settings")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("not valid TOML", result.stdout)
            self.assertEqual((home / "config.toml").read_bytes(), malformed)

    def test_multiline_strings_do_not_confuse_table_detection(self) -> None:
        config = '''developer_instructions = """
[agents]
enabled = false
"""

[agents]
enabled = true
max_concurrent_threads_per_session = 40
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "medium"
'''
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "config.toml").write_text(config, encoding="utf-8")
            result = run_cli(home, "status")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("READY", result.stdout)


if __name__ == "__main__":
    unittest.main()
