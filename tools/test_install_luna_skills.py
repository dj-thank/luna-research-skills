from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install_luna_skills as installer


class LunaSkillInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.target = self.root / "profile" / ".agents" / "skills"
        self.source.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_skill(self, name: str, *, body: str = "instructions\n") -> Path:
        package = self.source / name
        (package / "references").mkdir(parents=True)
        (package / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            f'description: "Use {name} for a focused test."\n'
            "---\n\n"
            + body,
            encoding="utf-8",
        )
        (package / "references" / "guide.md").write_text(
            f"# {name}\n", encoding="utf-8"
        )
        return package

    @unittest.skipUnless(os.name == "nt", "Windows junction support")
    def test_reserved_package_replaced_with_junction_denied_before_write(self) -> None:
        self.make_skill("alpha")
        outside = self.root / "outside"
        outside.mkdir()
        plan = installer.build_plan(self.source, self.target)
        reserve = installer._reserve_destination
        destination = self.target / "alpha"

        def replace_with_junction(path):
            reserve(path)
            path.rmdir()
            subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(outside)],
                           check=True, capture_output=True)

        try:
            with mock.patch.object(installer, "_reserve_destination", side_effect=replace_with_junction):
                with self.assertRaisesRegex(installer.InstallError, "reparse|pin"):
                    installer.install_skills(plan)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            if os.path.lexists(destination):
                os.rmdir(destination)  # Remove the fixture junction itself only.

    @unittest.skipUnless(os.name == "nt", "Windows namespace locking")
    def test_target_root_cannot_be_replaced_after_reservation(self) -> None:
        self.make_skill("alpha")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "alpha").mkdir()
        plan = installer.build_plan(self.source, self.target)
        reserve = installer._reserve_destination
        attempted = []

        def replace(destination):
            reserve(destination)
            attempted.append(True)
            # This rename must fail while the destination chain is pinned.
            self.target.rename(self.root / "parked")
            os.symlink(outside, self.target, target_is_directory=True)

        with mock.patch.object(installer, "_reserve_destination", side_effect=replace):
            with self.assertRaises(installer.InstallError):
                installer.install_skills(plan)
        self.assertTrue(attempted)
        self.assertEqual(list((outside / "alpha").iterdir()), [])
        self.assertFalse((self.root / "parked").exists())
        self.assertFalse((self.target / "alpha" / "SKILL.md").exists())

    @unittest.skipUnless(os.name == "nt", "Windows namespace locking")
    def test_parent_remains_pinned_between_check_and_file_open(self) -> None:
        self.make_skill("alpha")
        plan = installer.build_plan(self.source, self.target)
        original_open = Path.open
        blocked = []

        def try_replace(path, mode="r", *args, **kwargs):
            if mode == "xb":
                try:
                    path.parent.rename(path.parent.with_name(path.parent.name + "-moved"))
                except OSError:
                    blocked.append(path)
                else:
                    self.fail("destination directory could be replaced before open")
            return original_open(path, mode, *args, **kwargs)

        with mock.patch.object(Path, "open", try_replace):
            installer.install_skills(plan)
        self.assertEqual(len(blocked), 2)
        installer.verify_installation(self.source, self.target)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor-relative writes")
    def test_posix_file_creation_does_not_follow_swapped_parent(self) -> None:
        self.make_skill("alpha")
        outside = self.root / "outside"
        (outside / "alpha" / "references").mkdir(parents=True)
        plan = installer.build_plan(self.source, self.target)
        original_open = os.open
        swapped = []
        attempted = []

        def replace_before_open(path, flags, *args, **kwargs):
            if flags & os.O_CREAT and not attempted:
                attempted.append(True)
                try:
                    self.target.rename(self.root / "parked")
                except OSError:
                    # Some POSIX-backed Windows mounts deny rename while the
                    # directory fd is open, providing stronger namespace pinning.
                    pass
                else:
                    self.target.symlink_to(outside, target_is_directory=True)
                    swapped.append(True)
            return original_open(path, flags, *args, **kwargs)

        try:
            failure = None
            with mock.patch.object(os, "open", side_effect=replace_before_open):
                try:
                    installer.install_skills(plan)
                except installer.InstallError as exc:
                    failure = exc
            self.assertTrue(attempted)
            if swapped:
                self.assertIsNotNone(failure)
            else:
                self.assertIsNone(failure)
                installer.verify_installation(self.source, self.target)
            self.assertEqual(list(outside.rglob("*.md")), [])
        finally:
            if self.target.is_symlink():
                self.target.unlink()

    def test_default_source_supports_repository_and_plugin_layouts(self) -> None:
        repository = self.root / "repository"
        plugin = self.root / "plugin"
        (repository / ".agents/skills").mkdir(parents=True)
        (repository / "skills").mkdir()
        (plugin / "skills").mkdir(parents=True)

        self.assertEqual(
            installer.default_source(repository), repository / ".agents/skills"
        )
        self.assertEqual(installer.default_source(plugin), plugin / "skills")

    def test_plan_is_non_mutating(self) -> None:
        self.make_skill("alpha")
        plan = installer.build_plan(self.source, self.target)
        self.assertEqual([skill.name for skill in plan.skills], ["alpha"])
        self.assertFalse(self.target.exists())

    def test_apply_and_verify_preserve_exact_files(self) -> None:
        self.make_skill("alpha")
        self.make_skill("beta")
        plan = installer.build_plan(self.source, self.target)
        installer.install_skills(plan)
        verified = installer.verify_installation(self.source, self.target)
        self.assertEqual([skill.name for skill in verified.skills], ["alpha", "beta"])
        self.assertEqual(
            (self.source / "alpha/SKILL.md").read_bytes(),
            (self.target / "alpha/SKILL.md").read_bytes(),
        )

    def test_existing_destination_refuses_before_any_install(self) -> None:
        self.make_skill("alpha")
        self.make_skill("beta")
        existing = self.target / "beta"
        existing.mkdir(parents=True)
        sentinel = existing / "keep.txt"
        sentinel.write_text("user data", encoding="utf-8")

        with self.assertRaisesRegex(installer.InstallError, "refusing to overwrite"):
            installer.build_plan(self.source, self.target)

        self.assertFalse((self.target / "alpha").exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "user data")

    def test_frontmatter_directory_mismatch_is_rejected(self) -> None:
        package = self.make_skill("alpha")
        text = (package / "SKILL.md").read_text(encoding="utf-8")
        (package / "SKILL.md").write_text(
            text.replace("name: alpha", "name: other"), encoding="utf-8"
        )
        with self.assertRaisesRegex(installer.InstallError, "does not match"):
            installer.build_plan(self.source, self.target)

    def test_modified_or_extra_installed_file_fails_verification(self) -> None:
        self.make_skill("alpha")
        plan = installer.build_plan(self.source, self.target)
        installer.install_skills(plan)
        (self.target / "alpha/references/guide.md").write_text(
            "changed\n", encoding="utf-8"
        )
        (self.target / "alpha/extra.txt").write_text("extra\n", encoding="utf-8")
        with self.assertRaisesRegex(installer.InstallError, "content mismatch"):
            installer.verify_installation(self.source, self.target)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support unavailable")
    def test_source_symlink_is_rejected_without_copying_external_data(self) -> None:
        package = self.make_skill("alpha")
        outside = self.root / "outside-secret.txt"
        outside.write_text("secret-value", encoding="utf-8")
        link = package / "references" / "external.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"cannot create source symlink: {exc}")

        with self.assertRaisesRegex(installer.InstallError, "symlink|reparse"):
            installer.build_plan(self.source, self.target)
        self.assertFalse(self.target.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support unavailable")
    def test_target_parent_symlink_is_rejected(self) -> None:
        self.make_skill("alpha")
        real_profile = self.root / "real-profile"
        real_profile.mkdir()
        profile_link = self.root / "linked-profile"
        try:
            profile_link.symlink_to(real_profile, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"cannot create directory symlink: {exc}")
        target = profile_link / ".agents" / "skills"

        with self.assertRaisesRegex(installer.InstallError, "symlink|reparse"):
            installer.build_plan(self.source, target)
        self.assertEqual(list(real_profile.iterdir()), [])

    def test_partial_write_failure_removes_unpublished_package(self) -> None:
        self.make_skill("alpha")
        plan = installer.build_plan(self.source, self.target)
        with mock.patch.object(installer.os, "fsync", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(installer.InstallError, "disk failure"):
                installer.install_skills(plan)
        self.assertFalse(self.target.exists())

    def test_destination_created_after_preflight_is_not_deleted(self) -> None:
        self.make_skill("alpha")
        plan = installer.build_plan(self.source, self.target)
        real_reserve = installer._reserve_destination

        def collide(destination: Path) -> None:
            destination.mkdir()
            (destination / "user.txt").write_text("concurrent user data", encoding="utf-8")
            real_reserve(destination)

        with mock.patch.object(installer, "_reserve_destination", side_effect=collide):
            with self.assertRaisesRegex(installer.InstallError, "manual inspection"):
                installer.install_skills(plan)

        sentinel = self.target / "alpha/user.txt"
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "concurrent user data")

    def test_second_package_failure_rolls_back_first_package(self) -> None:
        self.make_skill("alpha")
        self.make_skill("beta")
        plan = installer.build_plan(self.source, self.target)
        real_write = installer._write_reserved_skill
        calls = 0

        def fail_second_package(destination: Path, skill: installer.SkillSnapshot) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise installer.InstallError("injected second package failure")
            real_write(destination, skill)

        with mock.patch.object(
            installer, "_write_reserved_skill", side_effect=fail_second_package
        ):
            with self.assertRaisesRegex(
                installer.InstallError, "injected second package failure"
            ):
                installer.install_skills(plan)

        self.assertFalse((self.target / "alpha").exists())
        self.assertFalse((self.target / "beta").exists())
        self.assertFalse(self.target.exists())

    def test_rollback_preserves_unexpected_ignored_artifact_and_original_package(self) -> None:
        self.make_skill("alpha")
        self.make_skill("beta")
        plan = installer.build_plan(self.source, self.target)
        real_write = installer._write_reserved_skill
        calls = 0

        def add_concurrent_file_then_fail(
            destination: Path, skill: installer.SkillSnapshot
        ) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                cache = self.target / "alpha/__pycache__"
                cache.mkdir()
                (cache / "user.pyc").write_bytes(b"concurrent-user-data")
                raise installer.InstallError("injected failure after concurrent write")
            real_write(destination, skill)

        with mock.patch.object(
            installer,
            "_write_reserved_skill",
            side_effect=add_concurrent_file_then_fail,
        ):
            with self.assertRaisesRegex(installer.InstallError, "manual inspection"):
                installer.install_skills(plan)

        alpha = self.target / "alpha"
        self.assertEqual(
            (alpha / "__pycache__/user.pyc").read_bytes(), b"concurrent-user-data"
        )
        self.assertTrue((alpha / "SKILL.md").is_file())
        self.assertTrue((alpha / "references/guide.md").is_file())
        self.assertFalse((self.target / "beta").exists())

    def test_case_insensitive_file_collision_is_rejected(self) -> None:
        package = self.make_skill("alpha")
        (package / "A.txt").write_text("one", encoding="utf-8")
        (package / "a.TXT").write_text("two", encoding="utf-8")
        if len({entry.name for entry in package.iterdir()}) < 4:
            self.skipTest("filesystem is already case-insensitive")
        with self.assertRaisesRegex(installer.InstallError, "case-insensitive"):
            installer.build_plan(self.source, self.target)

    def test_json_cli_reports_plan_and_error_without_traceback(self) -> None:
        self.make_skill("alpha")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = installer.main(
                [
                    "--source",
                    str(self.source),
                    "--target-root",
                    str(self.target),
                    "--json",
                ]
            )
        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "PLAN")
        self.assertEqual(payload["skills"][0]["name"], "alpha")
        self.assertFalse(self.target.exists())

        error_output = io.StringIO()
        with contextlib.redirect_stdout(error_output):
            result = installer.main(
                [
                    "--source",
                    str(self.root / "missing"),
                    "--target-root",
                    str(self.target),
                    "--json",
                ]
            )
        self.assertEqual(result, 2)
        error_payload = json.loads(error_output.getvalue())
        self.assertEqual(error_payload["status"], "ERROR")
        self.assertNotIn("Traceback", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
