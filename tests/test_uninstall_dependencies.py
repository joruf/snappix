"""
Unit tests for Snappix uninstall/deinstall flow.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import uninstall_dependencies as uninstaller
from src.install_manifest import InstallManifest, save_manifest


class TestUninstallDependencies(unittest.TestCase):
    """
    Verifies safe uninstall behavior driven by the install manifest.
    """

    def test_can_safely_remove_only_snappix_owned_apt_packages(self) -> None:
        """
        Ensures apt removal is allowed only when extra removals are auto-installed.
        """

        owned = {"grim", "slurp"}
        with (
            patch.object(uninstaller, "is_system_package_installed", return_value=True),
            patch.object(uninstaller, "_apt_packages_marked_for_removal", return_value={"grim", "libgrim0"}),
            patch.object(uninstaller, "_apt_package_is_auto", side_effect=lambda pkg: pkg == "libgrim0"),
        ):
            self.assertTrue(uninstaller.can_safely_remove_system_package("apt-get", "grim", owned))
            self.assertFalse(uninstaller.can_safely_remove_system_package("apt-get", "slurp", owned))

    def test_uninstall_removes_recorded_user_files_and_venv(self) -> None:
        """
        Ensures uninstall removes manifest-tracked user files and the project venv.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            project_dir = tmp_root / "snappix"
            project_dir.mkdir()
            venv_dir = project_dir / ".venv"
            venv_dir.mkdir()
            (venv_dir / "bin").mkdir()
            user_file = tmp_root / "launcher.desktop"
            user_file.write_text("desktop", encoding="utf-8")
            manifest = InstallManifest(
                project_dir=str(project_dir),
                venv_created=True,
                user_files=[str(user_file)],
            )
            manifest_path = tmp_root / "install-manifest.json"

            with (
                patch("src.install_manifest.manifest_path", return_value=manifest_path),
                patch.object(uninstaller, "remove_system_packages", return_value=([], [])),
                patch("uninstall_dependencies.clear_manifest") as clear_mock,
                patch("builtins.input", return_value="y"),
            ):
                save_manifest(manifest)
                code = uninstaller.uninstall(assume_yes=False)

            self.assertEqual(code, 0)
            self.assertFalse(venv_dir.exists())
            self.assertFalse(user_file.exists())
            clear_mock.assert_called_once()

    def test_uninstall_skips_packages_not_owned_by_snappix(self) -> None:
        """
        Ensures uninstall never attempts to remove packages outside the manifest.
        """

        manifest = InstallManifest(
            package_manager="apt-get",
            system_packages_installed=["grim"],
        )
        with (
            patch("uninstall_dependencies.load_manifest", return_value=manifest),
            patch.object(
                uninstaller,
                "can_safely_remove_system_package",
                return_value=False,
            ) as safe_mock,
            patch.object(uninstaller, "remove_user_files", return_value=[]),
            patch.object(uninstaller, "remove_virtual_environment", return_value=None),
            patch.object(uninstaller, "remove_initialized_marker", return_value=None),
            patch.object(uninstaller, "clear_manifest") as clear_mock,
        ):
            removed, skipped = uninstaller.remove_system_packages(manifest)

        safe_mock.assert_called_once_with("apt-get", "grim", {"grim"})
        clear_mock.assert_not_called()
        self.assertEqual(removed, [])
        self.assertEqual(skipped, ["grim"])


if __name__ == "__main__":
    unittest.main()
