import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import validate_repository as validator


class RepositoryValidatorTests(unittest.TestCase):
    def fixture(self) -> Path:
        root = Path(tempfile.mkdtemp())
        for name, implicit in (
            ("run-diverse-luna-project", "true"),
            ("run-diverse-luna-research", "true"),
        ):
            package = root / ".agents" / "skills" / name
            (package / "agents").mkdir(parents=True)
            (package / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: test\n---\n", encoding="utf-8"
            )
            (package / "agents" / "openai.yaml").write_text(
                "interface:\n"
                "  display_name: X\n"
                "  short_description: X\n"
                "  default_prompt: X\n"
                "policy:\n"
                f"  allow_implicit_invocation: {implicit}\n",
                encoding="utf-8",
            )
            scripts = package / "scripts"
            scripts.mkdir()
            (scripts / "check_setup.py").write_text("# checker\n", encoding="utf-8")
            (scripts / "test_check_setup.py").write_text("# tests\n", encoding="utf-8")
        (root / ".codex" / "agents").mkdir(parents=True)
        for index in range(5):
            (root / ".codex" / "agents" / f"{index}.toml").write_text(
                f'name = "agent-{index}"\ndescription = "d"\ndeveloper_instructions = "i"\n',
                encoding="utf-8",
            )
        (root / ".codex-plugin").mkdir()
        (root / ".codex-plugin" / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "x",
                    "version": "1.0.0",
                    "description": "x",
                    "author": {"name": "x"},
                    "interface": {"displayName": "x", "shortDescription": "x"},
                    "skills": "./skills/",
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_good_repo_passes(self):
        self.assertEqual(validator.validate_repository(self.fixture()), [])

    def test_malformed_toml_is_structured(self):
        root = self.fixture()
        (root / ".codex/agents/0.toml").write_bytes(b"name = [\xff")
        self.assertIn("toml_error", {e["code"] for e in validator.validate_repository(root)})

    def test_duplicate_case_and_missing_link(self):
        root = self.fixture()
        (root / ".codex/agents/1.toml").write_text(
            'name="AGENT-0"\ndescription="d"\ndeveloper_instructions="i"', encoding="utf-8"
        )
        (root / "README.md").write_text("[x](missing.md)", encoding="utf-8")
        codes = {e["code"] for e in validator.validate_repository(root)}
        self.assertIn("duplicate_agent_name", codes)
        self.assertIn("missing_link", codes)

    def test_plugin_manifest_is_optional_for_source_repository(self):
        root = self.fixture()
        (root / ".codex-plugin/plugin.json").unlink()
        (root / ".codex-plugin").rmdir()
        self.assertEqual(validator.validate_repository(root), [])

    def test_unsafe_agent_policy_and_bad_plugin_path_are_rejected(self):
        root = self.fixture()
        (root / ".codex/agents/0.toml").write_text(
            'name="agent-0"\ndescription="d"\ndeveloper_instructions="i"\napproval_policy="never"\n',
            encoding="utf-8",
        )
        manifest_path = root / ".codex-plugin/plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skills"] = "./.agents/skills"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        codes = {e["code"] for e in validator.validate_repository(root)}
        self.assertIn("unsafe_agent_policy", codes)
        self.assertIn("plugin_manifest", codes)

    def test_unpinned_action_and_machine_path_are_rejected(self):
        root = self.fixture()
        workflows = root / ".github/workflows"
        workflows.mkdir(parents=True)
        (workflows / "bad.yml").write_text(
            "steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8"
        )
        windows_path = "C:" + "\\Users\\" + "alice\\secret.txt\n"
        (root / "LEAK.md").write_text(windows_path, encoding="utf-8")
        codes = {e["code"] for e in validator.validate_repository(root)}
        self.assertIn("unpinned_action", codes)
        self.assertIn("machine_user_path", codes)

    def test_machine_paths_across_platforms_and_builtin_override_are_rejected(self):
        root = self.fixture()
        windows_path = "C:" + "\\Users\\" + "path\\private.txt\n"
        linux_path = "/" + "home/alice/private.txt\n"
        mac_path = "/" + "Users/bob/private.txt\n"
        (root / "LEAKS.md").write_text(windows_path + linux_path + mac_path, encoding="utf-8")
        (root / ".codex/agents/0.toml").write_text(
            'name="worker"\ndescription="d"\ndeveloper_instructions="i"\n', encoding="utf-8"
        )
        codes = [e["code"] for e in validator.validate_repository(root)]
        self.assertIn("machine_user_path", codes)
        self.assertIn("builtin_agent_override", codes)

    def test_implicit_discovery_contract_is_fail_closed(self):
        root = self.fixture()
        research = root / ".agents/skills/run-diverse-luna-research/agents/openai.yaml"
        research.write_text(
            research.read_text(encoding="utf-8").replace(
                "allow_implicit_invocation: true", "allow_implicit_invocation: false"
            ),
            encoding="utf-8",
        )
        self.assertIn("implicit_router", {e["code"] for e in validator.validate_repository(root)})

    def test_release_workflow_requires_immutable_publication_assertion(self):
        root = self.fixture()
        (root / "VERSION").write_text("2.0.3\n", encoding="utf-8")
        workflows = root / ".github/workflows"
        workflows.mkdir(parents=True)
        (workflows / "release.yml").write_text(
            "on:\n  workflow_dispatch:\n"
            "steps:\n"
            "  - run: test \"${GITHUB_REF_TYPE}\" = \"tag\"\n"
            "  - run: gh release create \"${GITHUB_REF_NAME}\" release/* --verify-tag\n",
            encoding="utf-8",
        )
        errors = validator.validate_repository(root)
        self.assertIn("release_workflow", {error["code"] for error in errors})
        self.assertTrue(any("immutability" in error["message"] for error in errors))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support unavailable")
    def test_symlink_source_is_rejected_without_reading_target(self):
        root = self.fixture()
        outside = Path(tempfile.mkdtemp()) / "secret.md"
        outside.write_text("outside-secret", encoding="utf-8")
        link = root / "linked.md"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"cannot create symlink: {exc}")
        errors = validator.validate_repository(root)
        self.assertIn("reparse_source", {e["code"] for e in errors})
        self.assertFalse(any("outside-secret" in e["message"] for e in errors))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support unavailable")
    def test_agent_toml_symlink_is_rejected_before_parse(self):
        root = self.fixture()
        outside = Path(tempfile.mkdtemp()) / "agent.toml"
        outside.write_text(
            'name="outside-agent"\ndescription="external-secret"\ndeveloper_instructions="i"\n',
            encoding="utf-8",
        )
        link = root / ".codex/agents/0.toml"
        link.unlink()
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"cannot create agent symlink: {exc}")
        errors = validator.validate_repository(root)
        self.assertIn("reparse_source", {e["code"] for e in errors})
        self.assertFalse(any("external-secret" in e["message"] for e in errors))

    @unittest.skipUnless(os.name == "nt", "junction fixture is Windows-specific")
    def test_junction_directory_is_rejected_without_traversal(self):
        root = self.fixture()
        outside = Path(tempfile.mkdtemp())
        (outside / "secret.md").write_text("junction-secret", encoding="utf-8")
        junction = root / "junction"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest(f"cannot create junction: {result.stderr or result.stdout}")
        try:
            errors = validator.validate_repository(root)
            self.assertIn("reparse_source", {e["code"] for e in errors})
            self.assertFalse(any("junction-secret" in e["message"] for e in errors))
        finally:
            os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "junction fixture is Windows-specific")
    def test_agent_parent_junction_is_rejected_without_parse(self):
        root = self.fixture()
        agents = root / ".codex/agents"
        outside = Path(tempfile.mkdtemp()) / "external-agents"
        agents.rename(outside)
        (outside / "0.toml").write_text(
            'name="outside-agent"\ndescription="junction-secret"\ndeveloper_instructions="i"\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(agents), str(outside)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest(f"cannot create agent junction: {result.stderr or result.stdout}")
        try:
            errors = validator.validate_repository(root)
            self.assertIn("reparse_source", {e["code"] for e in errors})
            self.assertFalse(any("junction-secret" in e["message"] for e in errors))
        finally:
            os.rmdir(agents)


if __name__ == "__main__":
    unittest.main()
