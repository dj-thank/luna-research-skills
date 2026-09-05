from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_release import build


class ReleaseBuilderTests(unittest.TestCase):
    def test_plugin_keeps_readme_diagram_and_local_document_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            (root / "VERSION").write_text("2.0.0\n", encoding="utf-8")
            readme = "![Teams](docs/assets/teams.png)\n[Skill](.agents/skills/demo/SKILL.md)\n[Migration](tools/MIGRATION.md)\n[Development](CONTRIBUTING.md)\n"
            (root / "README.md").write_text(readme, encoding="utf-8")
            files = {
                ".agents/skills/demo/SKILL.md": b"skill",
                "docs/assets/teams.png": b"\x89PNG\r\n\x1a\nfixture",
                "docs/evaluation.md": b"bounded evaluation",
                "tools/MIGRATION.md": b"migration procedure",
                "CONTRIBUTING.md": b"development procedure",
                "CHANGELOG.md": b"changes",
                ".codex/agents/demo.toml": b"custom agent intentionally excluded",
            }
            for name, data in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            outputs = build(root, Path(temp) / "out")
            with zipfile.ZipFile(outputs["plugin"]) as plugin:
                self.assertEqual(plugin.read("docs/assets/teams.png"), files["docs/assets/teams.png"])
                for name in ("docs/evaluation.md", "tools/MIGRATION.md", "CONTRIBUTING.md", "CHANGELOG.md"):
                    self.assertIn(name, plugin.namelist())
                self.assertIn("[Skill](skills/demo/SKILL.md)", plugin.read("README.md").decode("utf-8"))
                self.assertNotIn(".codex/agents/demo.toml", plugin.namelist())
            self.assertEqual((root / "README.md").read_text(encoding="utf-8"), readme)

    def test_reproducible_archive_and_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            (root / "VERSION").write_text("2.0.0\n", encoding="utf-8")
            (root / "README.md").write_text("hello\n", encoding="utf-8")
            skill = root / ".agents" / "skills" / "run-diverse-luna-research"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("skill\n", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "bad.pyc").write_bytes(b"bad")
            (root / "dist").mkdir()
            (root / "dist" / "old.zip").write_bytes(b"bad")
            out1, out2 = Path(temp) / "one", Path(temp) / "two"
            first, second = build(root, out1), build(root, out2)
            self.assertEqual(hashlib.sha256(first["archive"].read_bytes()).digest(), hashlib.sha256(second["archive"].read_bytes()).digest())
            with zipfile.ZipFile(first["archive"]) as archive:
                self.assertEqual(archive.namelist(), [".agents/skills/run-diverse-luna-research/SKILL.md", "README.md", "VERSION"])
                self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))
                archive.testzip()
            with zipfile.ZipFile(first["plugin"]) as plugin:
                names = plugin.namelist()
                self.assertTrue(all(not name.startswith("/") and ".." not in Path(name).parts for name in names))
                self.assertIn(".codex-plugin/plugin.json", names)
                self.assertIn("skills/run-diverse-luna-research/SKILL.md", names)
                canonical = (skill / "SKILL.md").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                self.assertEqual(hashlib.sha256(plugin.read("skills/run-diverse-luna-research/SKILL.md")).digest(), hashlib.sha256(canonical).digest())
                self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in plugin.infolist()))
                plugin.testzip()
                manifest = json.loads(plugin.read(".codex-plugin/plugin.json"))
                self.assertEqual(manifest["version"], "2.0.0")
                self.assertEqual(manifest["skills"], "./skills/")
                self.assertEqual(manifest["author"]["name"], "dj-thank")
                self.assertIn("description", manifest)
                self.assertIn("displayName", manifest["interface"])
            sbom = json.loads(first["sbom"].read_text(encoding="utf-8"))
            self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
            self.assertEqual(sbom["creationInfo"]["created"], "1980-01-01T00:00:00Z")
            sums = first["sums"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(sums), 3)
            self.assertTrue(any(first["sbom"].name in line for line in sums))
            checksums = {item["fileName"]: item["checksums"][0]["checksumValue"] for item in sbom["files"]}
            with zipfile.ZipFile(first["archive"]) as source_zip:
                for name in source_zip.namelist():
                    self.assertEqual(checksums[name], hashlib.sha256(source_zip.read(name)).hexdigest())

    def test_nonempty_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            (root / "VERSION").write_text("2.0.0\n", encoding="utf-8")
            (root / "README.md").write_text("hello\n", encoding="utf-8")
            output = Path(temp) / "release"
            output.mkdir()
            (output / "stale.zip").write_bytes(b"stale")
            with self.assertRaisesRegex(ValueError, "new or empty"):
                build(root, output)

    def test_text_line_endings_are_canonical_across_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            roots = []
            for label, newline in (("lf", b"\n"), ("crlf", b"\r\n")):
                root = Path(temp) / label
                skill = root / ".agents" / "skills" / "run-diverse-luna-research"
                skill.mkdir(parents=True)
                (root / "VERSION").write_bytes(b"2.0.4" + newline)
                (root / "README.md").write_bytes(b"hello" + newline)
                (root / "LICENSE").write_bytes(b"license" + newline)
                (skill / "SKILL.md").write_bytes(b"skill" + newline)
                roots.append(root)

            left = build(roots[0], Path(temp) / "left")
            right = build(roots[1], Path(temp) / "right")
            for key in ("archive", "plugin", "sums", "sbom"):
                self.assertEqual(
                    hashlib.sha256(left[key].read_bytes()).digest(),
                    hashlib.sha256(right[key].read_bytes()).digest(),
                    key,
                )
            with zipfile.ZipFile(right["archive"]) as archive:
                self.assertEqual(archive.read("README.md"), b"hello\n")
                self.assertEqual(archive.read("LICENSE"), b"license\n")


if __name__ == "__main__":
    unittest.main()
