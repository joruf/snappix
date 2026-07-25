"""
Unit tests for Snappix first-time dependency installation.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import install_dependencies as installer
from src.install_progress_gui import map_installer_line_to_status, summarize_installer_failure


class TestInstallDependencies(unittest.TestCase):
    """
    Verifies bootstrap behavior for required vs recommended system packages.
    """

    def test_recommended_only_missing_skips_pkexec_in_gui_mode(self) -> None:
        """
        Ensures missing grim/slurp alone never triggers GUI elevation or failure.
        """

        project_dir = Path("/tmp/snappix-test")
        with (
            patch.object(installer, "detect_missing_system_dependencies", return_value=[]),
            patch.object(
                installer,
                "detect_missing_recommended_dependencies",
                side_effect=[["grim", "slurp"], ["grim", "slurp"]],
            ),
            patch.object(installer, "detect_package_manager", return_value="apt-get"),
            patch.object(installer, "_gui_mode_needs_pkexec", return_value=True),
            patch.object(installer, "_elevate_system_install") as elevate_mock,
            patch.object(installer, "_run_package_commands") as run_packages_mock,
        ):
            code = installer.install_system_dependencies(project_dir)

        self.assertEqual(code, 0)
        elevate_mock.assert_not_called()
        run_packages_mock.assert_not_called()

    def test_required_present_tries_recommended_in_tty_mode(self) -> None:
        """
        Ensures console mode may install recommended packages without failing bootstrap.
        """

        project_dir = Path("/tmp/snappix-test")
        with (
            patch.object(installer, "detect_missing_system_dependencies", return_value=[]),
            patch.object(
                installer,
                "detect_missing_recommended_dependencies",
                side_effect=[["grim"], []],
            ),
            patch.object(installer, "detect_package_manager", return_value="apt-get"),
            patch.object(installer, "_gui_mode_needs_pkexec", return_value=False),
            patch.object(installer, "packages_not_installed", return_value=["grim"]),
            patch.object(installer, "_run_package_commands", return_value=1) as run_packages_mock,
        ):
            code = installer.install_system_dependencies(project_dir)

        self.assertEqual(code, 0)
        run_packages_mock.assert_called_once()

    def test_pkexec_failure_is_soft_when_required_already_present(self) -> None:
        """
        Ensures a cancelled admin dialog does not fail when required packages exist.
        """

        project_dir = Path("/tmp/snappix-test")
        with (
            patch.object(
                installer,
                "detect_missing_system_dependencies",
                side_effect=[["xdotool"], []],
            ),
            patch.object(installer, "detect_missing_recommended_dependencies", return_value=[]),
            patch.object(installer, "detect_package_manager", return_value="apt-get"),
            patch.object(installer, "_gui_mode_needs_pkexec", return_value=True),
            patch.object(installer, "_elevate_system_install", return_value=126),
        ):
            code = installer.install_system_dependencies(project_dir)

        self.assertEqual(code, 0)

    def test_bootstrap_continues_python_install_after_system_warning(self) -> None:
        """
        Ensures venv/pip still succeed when system elevation fails.
        """

        project_dir = Path("/tmp/snappix-test")
        with (
            patch.object(installer, "install_system_dependencies", return_value=1),
            patch.object(installer, "ensure_venv", return_value=0) as venv_mock,
            patch.object(installer, "install_packages", return_value=0) as pip_mock,
            patch.object(
                installer,
                "detect_missing_system_dependencies",
                return_value=["tesseract"],
            ),
        ):
            code = installer.bootstrap(project_dir, "/usr/bin/python3")

        self.assertEqual(code, 0)
        venv_mock.assert_called_once_with(project_dir, "/usr/bin/python3")
        pip_mock.assert_called_once_with(project_dir)

    def test_bootstrap_fails_when_venv_cannot_be_created(self) -> None:
        """
        Ensures missing python3-venv still fails the installer clearly.
        """

        project_dir = Path("/tmp/snappix-test")
        with (
            patch.object(installer, "install_system_dependencies", return_value=0),
            patch.object(installer, "ensure_venv", return_value=1),
            patch.object(installer, "install_packages") as pip_mock,
        ):
            code = installer.bootstrap(project_dir, "/usr/bin/python3")

        self.assertEqual(code, 1)
        pip_mock.assert_not_called()

    def test_build_install_commands_for_apt(self) -> None:
        """
        Ensures apt commands include update plus package install.
        """

        commands = installer._build_install_commands("apt-get", ["grim", "slurp"])
        self.assertEqual(commands[0], ["apt-get", "update"])
        self.assertEqual(commands[1], ["apt-get", "install", "-y", "grim", "slurp"])

    def test_install_records_only_newly_installed_system_packages(self) -> None:
        """
        Ensures the install manifest records packages absent before installation only.
        """

        project_dir = Path("/tmp/snappix-test")
        with (
            patch.object(installer, "packages_not_installed", return_value=["grim", "slurp"]),
            patch.object(installer, "_run_package_commands", return_value=0) as run_packages_mock,
            patch.object(installer, "is_system_package_installed", side_effect=lambda _pm, pkg: pkg == "grim"),
            patch.object(installer, "record_project_dir") as record_project_mock,
            patch.object(installer, "record_package_manager") as record_manager_mock,
            patch.object(installer, "record_system_packages_installed") as record_packages_mock,
        ):
            code = installer._install_packages_with_tracking(project_dir, "apt-get", ["grim", "slurp"])

        self.assertEqual(code, 0)
        run_packages_mock.assert_called_once()
        record_project_mock.assert_called_once_with(project_dir)
        record_manager_mock.assert_called_once_with("apt-get")
        record_packages_mock.assert_called_once_with(["grim"])


class TestInstallProgressGuiHelpers(unittest.TestCase):
    """
    Verifies installer GUI status mapping and failure summaries.
    """

    def test_map_installer_line_to_status(self) -> None:
        """
        Ensures key installer log lines map to progress status text.
        """

        self.assertIn(
            "administrator",
            map_installer_line_to_status(
                "Snappix installer: requesting administrator rights via pkexec..."
            ).lower(),
        )
        self.assertIn(
            "virtual environment",
            map_installer_line_to_status(
                "Snappix installer: creating virtual environment..."
            ).lower(),
        )
        self.assertIsNone(map_installer_line_to_status("   "))

    def test_summarize_installer_failure_prefers_error_lines(self) -> None:
        """
        Ensures failure dialogs surface error/warning lines first.
        """

        summary = summarize_installer_failure(
            [
                "Snappix installer: creating virtual environment...",
                "Snappix installer error: could not create .venv.",
                "Snappix installer warning: recommended tools still missing: grim",
            ]
        )
        self.assertIn("could not create .venv", summary)
        self.assertIn("recommended tools still missing", summary)


if __name__ == "__main__":
    unittest.main()
