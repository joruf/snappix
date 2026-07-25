"""
Unit tests for Snappix install manifest tracking.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.install_manifest import (
    InstallManifest,
    load_manifest,
    manifest_venv_dir,
    record_project_dir,
    record_system_packages_installed,
    record_user_file,
    record_venv_created,
    save_manifest,
)


class TestInstallManifest(unittest.TestCase):
    """
    Verifies install manifest persistence and path normalization.
    """

    def test_save_and_load_manifest_round_trip(self) -> None:
        """
        Ensures manifest fields survive a save/load cycle.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_file = Path(tmp_dir) / "install-manifest.json"
            manifest = InstallManifest(
                project_dir="/opt/snappix",
                package_manager="apt-get",
                system_packages_installed=["grim", "slurp"],
                venv_created=True,
                user_files=[".local/share/applications/snappix.desktop"],
            )
            with patch("src.install_manifest.manifest_path", return_value=manifest_file):
                save_manifest(manifest)
                loaded = load_manifest()

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.project_dir, "/opt/snappix")
            self.assertEqual(loaded.package_manager, "apt-get")
            self.assertEqual(loaded.system_packages_installed, ["grim", "slurp"])
            self.assertTrue(loaded.venv_created)

    def test_record_helpers_merge_without_duplicates(self) -> None:
        """
        Ensures repeated manifest updates append unique packages and files only once.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_file = Path(tmp_dir) / "install-manifest.json"
            with patch("src.install_manifest.manifest_path", return_value=manifest_file):
                record_project_dir("/home/user/snappix")
                record_system_packages_installed(["grim"])
                record_system_packages_installed(["grim", "slurp"])
                record_user_file(Path.home() / ".local/share/icons/hicolor/scalable/apps/snappix.svg")
                record_venv_created("/home/user/snappix")
                loaded = load_manifest()

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.system_packages_installed, ["grim", "slurp"])
            self.assertEqual(len(loaded.user_files), 1)
            self.assertTrue(loaded.venv_created)
            self.assertEqual(manifest_venv_dir(loaded), Path("/home/user/snappix/.venv"))

    def test_manifest_version_is_written(self) -> None:
        """
        Ensures the manifest JSON includes the schema version field.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_file = Path(tmp_dir) / "install-manifest.json"
            with patch("src.install_manifest.manifest_path", return_value=manifest_file):
                save_manifest(InstallManifest())
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)


if __name__ == "__main__":
    unittest.main()
