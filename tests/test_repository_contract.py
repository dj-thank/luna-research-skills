from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "luna-research-skills"
SKILLS = PLUGIN / "skills"


class RepositoryContractTests(unittest.TestCase):
    def test_plugin_and_marketplace_manifests_align(self) -> None:
        plugin = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        self.assertEqual(plugin["name"], "luna-research-skills")
        self.assertEqual(plugin["version"], "0.1.0")
        self.assertEqual(plugin["license"], "MIT")
        self.assertEqual(plugin["repository"], "https://github.com/dj-thank/luna-research-skills")
        self.assertEqual(plugin["skills"], "./skills/")
        self.assertEqual(marketplace["name"], "luna-research-skills")
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], plugin["name"])
        self.assertEqual(entry["source"]["path"], "./plugins/luna-research-skills")
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

    def test_skill_frontmatter_is_minimal_and_metadata_is_current(self) -> None:
        expected_policy = {
            "configure-luna-subagents": "false",
            "run-diverse-luna-research": "true",
        }
        for skill_dir in sorted(path for path in SKILLS.iterdir() if path.is_dir()):
            skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            match = re.match(r"\A---\n(.*?)\n---\n", skill_text, flags=re.DOTALL)
            self.assertIsNotNone(match, skill_dir.name)
            frontmatter = match.group(1).splitlines()  # type: ignore[union-attr]
            keys = {line.split(":", 1)[0] for line in frontmatter if ":" in line}
            self.assertEqual(keys, {"name", "description"}, skill_dir.name)
            self.assertIn(f"name: {skill_dir.name}", match.group(1))  # type: ignore[union-attr]
            self.assertLess(len(skill_text.splitlines()), 500, skill_dir.name)

            metadata = (skill_dir / "agents" / "openai.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"${skill_dir.name}", metadata)
            self.assertIn(
                f"allow_implicit_invocation: {expected_policy[skill_dir.name]}", metadata
            )

    def test_packaged_files_have_no_placeholders_or_machine_paths(self) -> None:
        forbidden = ("[TODO:", "C:\\Users\\", "rambo", "019f6b82-")
        text_suffixes = {".md", ".py", ".toml", ".yaml", ".json"}
        for path in PLUGIN.rglob("*"):
            if path.is_file() and path.suffix.lower() in text_suffixes:
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    self.assertNotIn(token, text, f"{token!r} found in {path}")

    def test_luna_asset_and_runtime_guardrails(self) -> None:
        asset = (
            SKILLS
            / "configure-luna-subagents"
            / "assets"
            / "default-agent.toml"
        )
        with asset.open("rb") as handle:
            role = tomllib.load(handle)
        self.assertEqual(role["name"], "default")
        self.assertEqual(role["model"], "gpt-5.6-luna")
        self.assertEqual(role["model_reasoning_effort"], "medium")

        research = (SKILLS / "run-diverse-luna-research" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('fork_turns="none"', research)
        self.assertIn("--runtime-thread", research)
        self.assertIn("Discard the packet", research)

    def test_public_repository_basics_exist(self) -> None:
        self.assertTrue((ROOT / "README.md").is_file())
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertTrue((ROOT / "SECURITY.md").is_file())
        self.assertTrue((ROOT / ".github" / "workflows" / "ci.yml").is_file())


if __name__ == "__main__":
    unittest.main()
