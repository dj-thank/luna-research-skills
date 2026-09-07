from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import release_metadata


class ReleaseMetadataTests(unittest.TestCase):
    def fixture(self, *, version: str = "2.0.6") -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "VERSION").write_text(version + "\n", encoding="utf-8")
        (root / "CHANGELOG.md").write_text(
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            f"## [{version}] - 2026-08-17\n\n"
            f"[Unreleased]: https://github.com/dj-thank/luna-research-skills/compare/v{version}...HEAD\n"
            f"[{version}]: https://github.com/dj-thank/luna-research-skills/compare/v2.0.5...v{version}\n",
            encoding="utf-8",
        )
        return root

    def test_consistent_metadata_passes(self) -> None:
        self.assertEqual(release_metadata.validate_release_metadata(self.fixture()), [])

    def test_stale_unreleased_base_and_missing_version_reference_fail(self) -> None:
        root = self.fixture()
        changelog = root / "CHANGELOG.md"
        changelog.write_text(
            changelog.read_text(encoding="utf-8")
            .replace("compare/v2.0.6...HEAD", "compare/v2.0.5...HEAD")
            .replace("[2.0.6]:", "[2.0.5]:"),
            encoding="utf-8",
        )
        codes = {error["code"] for error in release_metadata.validate_release_metadata(root)}
        self.assertIn("changelog_unreleased_base", codes)
        self.assertIn("changelog_version_reference", codes)

    def test_missing_or_duplicate_version_heading_fails(self) -> None:
        root = self.fixture()
        changelog = root / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        changelog.write_text(text + "\n## [2.0.6] - 2026-08-18\n", encoding="utf-8")
        errors = release_metadata.validate_release_metadata(root)
        self.assertTrue(
            any(error["code"] == "changelog_version_heading" for error in errors)
        )

    def test_release_heading_requires_date_and_unreleased_comes_first(self) -> None:
        root = self.fixture()
        changelog = root / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        text = text.replace("## [2.0.6] - 2026-08-17", "## [2.0.6]")
        changelog.write_text(text, encoding="utf-8")
        codes = {error["code"] for error in release_metadata.validate_release_metadata(root)}
        self.assertIn("changelog_version_heading", codes)

        root = self.fixture()
        changelog = root / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        text = text.replace(
            "## [Unreleased]\n\n## [2.0.6] - 2026-08-17",
            "## [2.0.6] - 2026-08-17\n\n## [Unreleased]",
        )
        changelog.write_text(text, encoding="utf-8")
        codes = {error["code"] for error in release_metadata.validate_release_metadata(root)}
        self.assertIn("changelog_section_order", codes)

    def test_invalid_calendar_date_and_wrong_repository_fail(self) -> None:
        root = self.fixture()
        changelog = root / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        text = text.replace("2026-08-17", "2026-02-30")
        text = text.replace(
            "github.com/dj-thank/luna-research-skills",
            "github.com/example/wrong-project",
        )
        changelog.write_text(text, encoding="utf-8")
        codes = {error["code"] for error in release_metadata.validate_release_metadata(root)}
        self.assertIn("changelog_version_date", codes)
        self.assertIn("changelog_unreleased_base", codes)
        self.assertIn("changelog_version_reference", codes)

    def test_semver_rejects_leading_zeroes(self) -> None:
        root = self.fixture(version="02.0.6")
        errors = release_metadata.validate_release_metadata(root)
        self.assertEqual([error["code"] for error in errors], ["version_format"])

    def test_invalid_version_is_reported_without_secondary_noise(self) -> None:
        root = self.fixture(version="version-two")
        errors = release_metadata.validate_release_metadata(root)
        self.assertEqual([error["code"] for error in errors], ["version_format"])

    def test_missing_files_are_structured_errors(self) -> None:
        root = Path(tempfile.mkdtemp())
        errors = release_metadata.validate_release_metadata(root)
        self.assertEqual(
            {error["code"] for error in errors},
            {"version_read", "changelog_read"},
        )


if __name__ == "__main__":
    unittest.main()
