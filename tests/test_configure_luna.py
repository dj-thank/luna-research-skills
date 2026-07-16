from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = (
    ROOT
    / "plugins"
    / "luna-research-skills"
    / "skills"
    / "configure-luna-subagents"
)
SCRIPT = SKILL / "scripts" / "configure_luna.py"
ROLE_ASSET = SKILL / "assets" / "default-agent.toml"


def run_cli(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--codex-home", str(home)],
        text=True,
        capture_output=True,
        check=False,
    )


class ConfigureLunaTests(unittest.TestCase):
    def test_plan_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = run_cli(home, "plan")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PLAN ONLY", result.stdout)
            self.assertFalse((home / "config.toml").exists())
            self.assertFalse((home / "agents" / "default.toml").exists())

    def test_clean_install_status_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installed = run_cli(home, "install", "--apply")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)

            with (home / "config.toml").open("rb") as handle:
                config = tomllib.load(handle)
            self.assertIs(config["features"]["multi_agent"], True)
            self.assertEqual(config["agents"]["max_threads"], 40)
            self.assertEqual(config["agents"]["max_depth"], 2)
            with (home / "agents" / "default.toml").open("rb") as handle:
                role = tomllib.load(handle)
            self.assertEqual(role["model"], "gpt-5.6-luna")

            status = run_cli(home, "status")
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("managed installation is intact", status.stdout)

            restored = run_cli(home, "uninstall", "--apply")
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            self.assertFalse((home / "config.toml").exists())
            self.assertFalse((home / "agents" / "default.toml").exists())
            self.assertFalse((home / ".luna-research-skills-state.json").exists())

    def test_conflicts_require_flags_and_restore_exact_originals(self) -> None:
        original_config = (
            b"title = \"preserve me\"\r\n\r\n"
            b"[features]\r\napps = true\r\nmulti_agent = false  # old\r\n\r\n"
            b"[agents]\r\nmax_threads = 8\r\nmax_depth = 1\r\n\r\n"
            b"[unrelated]\r\nvalue = 17\r\n"
        )
        original_role = b'name = "default"\nmodel = "another-model"\n'
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "agents").mkdir()
            (home / "config.toml").write_bytes(original_config)
            (home / "agents" / "default.toml").write_bytes(original_role)

            blocked = run_cli(home, "install", "--apply")
            self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
            self.assertIn("--replace-default", blocked.stdout)
            self.assertIn("--replace-settings", blocked.stdout)
            self.assertEqual((home / "config.toml").read_bytes(), original_config)
            self.assertEqual((home / "agents" / "default.toml").read_bytes(), original_role)

            installed = run_cli(
                home,
                "install",
                "--apply",
                "--replace-default",
                "--replace-settings",
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            patched = (home / "config.toml").read_text(encoding="utf-8")
            self.assertIn('title = "preserve me"', patched)
            self.assertIn("[unrelated]", patched)
            self.assertIn("value = 17", patched)

            restored = run_cli(home, "uninstall", "--apply")
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            self.assertEqual((home / "config.toml").read_bytes(), original_config)
            self.assertEqual((home / "agents" / "default.toml").read_bytes(), original_role)

    def test_drift_blocks_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installed = run_cli(home, "install", "--apply")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            config_path = home / "config.toml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8") + "# user edit\n",
                encoding="utf-8",
            )

            blocked = run_cli(home, "uninstall", "--apply")
            self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
            self.assertIn("changed after installation", blocked.stdout)
            self.assertTrue(config_path.read_text(encoding="utf-8").endswith("# user edit\n"))
            self.assertTrue((home / ".luna-research-skills-state.json").exists())

    def test_malformed_config_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            malformed = b"[features\nmulti_agent = true\n"
            (home / "config.toml").write_bytes(malformed)
            result = run_cli(home, "install", "--apply", "--replace-settings")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("not valid TOML", result.stdout)
            self.assertEqual((home / "config.toml").read_bytes(), malformed)

    def test_multiline_strings_do_not_confuse_table_detection(self) -> None:
        config = '''developer_instructions = """
[agents]
max_threads = 1
"""

[features]
multi_agent = true

[agents]
max_threads = 40
max_depth = 2
'''
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "agents").mkdir()
            (home / "config.toml").write_text(config, encoding="utf-8")
            (home / "agents" / "default.toml").write_bytes(ROLE_ASSET.read_bytes())
            result = run_cli(home, "status")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("READY", result.stdout)


if __name__ == "__main__":
    unittest.main()
