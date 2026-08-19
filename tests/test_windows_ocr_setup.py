"""
Tests for installing OCR on Windows without administrator rights.

The winget package behind Tesseract installs machine-wide and therefore needs
elevation, which locks out every Windows account that does not have it. These
tests pin down the two halves of the replacement: setup never demands elevation
by itself, and a Tesseract living in the project runtime folder is found and
used.

Windows is simulated -- no test here needs to run on Windows.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import install_dependencies
from src.tesseract_setup import (
    TESSERACT_INSTALLER_URL,
    bundled_tesseract_dir,
    bundled_tesseract_exe,
    build_silent_install_command,
    has_bundled_tesseract,
    install_for_current_user,
    tesseract_environment,
)


class TestSilentInstallCommand(unittest.TestCase):
    """
    Verifies the NSIS command line that avoids the elevation prompt.
    """

    def test_target_directory_is_passed_unquoted(self) -> None:
        """
        Ensures a path with spaces still reaches the installer.

        NSIS wants ``/D=`` unquoted and last. Quoting it -- which passing the
        arguments as a list would do -- makes the installer silently fall back
        to its machine-wide default directory, which then needs elevation.
        """

        command = build_silent_install_command(
            Path(r"C:\Temp\setup.exe"),
            Path(r"C:\Users\Max Mustermann\snappix\.snappix-runtime\tesseract"),
        )

        self.assertTrue(command.endswith(
            r"/D=C:\Users\Max Mustermann\snappix\.snappix-runtime\tesseract"
        ))
        self.assertNotIn('/D="', command)

    def test_installer_path_stays_quoted(self) -> None:
        """
        Ensures a project in a path with spaces can still be launched.
        """

        command = build_silent_install_command(
            Path(r"C:\Users\Max Mustermann\setup.exe"),
            Path(r"C:\Target"),
        )
        self.assertTrue(command.startswith('"C:\\Users\\Max Mustermann\\setup.exe"'))

    def test_silent_flag_precedes_the_directory(self) -> None:
        """
        Ensures the install runs without showing a window at all.
        """

        command = build_silent_install_command(Path("s.exe"), Path("t"))
        self.assertLess(command.index("/S"), command.index("/D="))

    def test_trailing_separator_is_removed(self) -> None:
        """
        Ensures the path is not swallowed by NSIS escaping.
        """

        command = build_silent_install_command(Path("s.exe"), Path("C:\\Target\\"))
        self.assertTrue(command.endswith("/D=C:\\Target"))

    def test_the_official_source_is_used(self) -> None:
        """
        Ensures the download comes from the same place the winget package uses,
        rather than some repackaged third-party build.
        """

        self.assertTrue(
            TESSERACT_INSTALLER_URL.startswith(
                "https://digi.bib.uni-mannheim.de/tesseract/"
            )
        )
        self.assertTrue(TESSERACT_INSTALLER_URL.endswith(".exe"))


class TestBundledLocation(unittest.TestCase):
    """
    Verifies where the per-user copy lives and how it is detected.
    """

    def test_it_lives_beside_the_other_managed_runtimes(self) -> None:
        """
        Ensures OCR follows the same pattern as the managed uv/Python runtime.
        """

        directory = bundled_tesseract_dir(Path("/project"))
        self.assertEqual(directory.parent.name, ".snappix-runtime")

    def test_detection_follows_the_executable(self) -> None:
        """
        Ensures a half-finished install is not mistaken for a working one.
        """

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            self.assertFalse(has_bundled_tesseract(project))

            executable = bundled_tesseract_exe(project)
            executable.parent.mkdir(parents=True)
            executable.write_text("stub")
            self.assertTrue(has_bundled_tesseract(project))

    def test_language_files_are_pointed_at(self) -> None:
        """
        Ensures the private copy can find its language data.

        Tesseract outside its original location does not locate ``tessdata`` on
        its own; without this it reports "Error opening data file".
        """

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            data_dir = bundled_tesseract_dir(project) / "tessdata"
            data_dir.mkdir(parents=True)

            environment = tesseract_environment(project)
            self.assertEqual(environment["TESSDATA_PREFIX"], str(data_dir))

    def test_no_language_path_is_invented_when_absent(self) -> None:
        """
        Ensures a system-wide Tesseract keeps using its own data.
        """

        with TemporaryDirectory() as temporary:
            self.assertNotIn("TESSDATA_PREFIX", tesseract_environment(Path(temporary)))


class TestNoElevationDuringSetup(unittest.TestCase):
    """
    Verifies that ordinary setup never triggers an elevation prompt.
    """

    def test_windows_setup_does_not_require_tesseract(self) -> None:
        """
        Ensures OCR cannot block installation on a locked-down account.

        Listing it as required made the installer reach for winget, whose
        Tesseract package installs machine-wide and prompts for administrator
        rights.
        """

        # which() must report nothing, otherwise the machine running the tests
        # would satisfy the check by accident and prove nothing.
        with patch("src.paths.is_windows", return_value=True), patch.object(
            install_dependencies, "which", return_value=None
        ):
            missing = install_dependencies.detect_missing_system_dependencies()

        self.assertNotIn("tesseract", missing)
        self.assertEqual(missing, [], "Windows setup must not demand any tool")

    def test_winget_is_never_asked_for_tesseract(self) -> None:
        """
        Ensures the elevating package is not installed behind the user's back.
        """

        self.assertNotIn("tesseract", install_dependencies.WINDOWS_WINGET_PACKAGES)
        self.assertNotIn(
            "UB-Mannheim.TesseractOCR",
            install_dependencies.WINDOWS_WINGET_PACKAGES.values(),
        )

    def test_ocr_install_is_opt_in(self) -> None:
        """
        Ensures the download only happens when the user asks for it.
        """

        with patch(
            "src.tesseract_setup.install_for_current_user", return_value=True
        ) as installer, patch("src.platform.has_tesseract", return_value=False), patch(
            "src.paths.is_windows", return_value=True
        ):
            install_dependencies.install_system_dependencies(Path("/project"))

        installer.assert_not_called()

    def test_the_opt_in_command_installs_per_user(self) -> None:
        """
        Ensures ``--install-ocr`` uses the per-user path, not winget.
        """

        with patch(
            "src.tesseract_setup.install_for_current_user", return_value=True
        ) as installer, patch("src.platform.has_tesseract", return_value=False), patch(
            "src.paths.is_windows", return_value=True
        ):
            code = install_dependencies.install_ocr_for_current_user(Path("/project"))

        self.assertEqual(code, 0)
        installer.assert_called_once()

    def test_already_available_ocr_downloads_nothing(self) -> None:
        """
        Ensures an existing system-wide Tesseract is left alone.
        """

        with patch("src.platform.has_tesseract", return_value=True), patch(
            "src.tesseract_setup.install_for_current_user"
        ) as installer:
            code = install_dependencies.install_ocr_for_current_user(Path("/project"))

        self.assertEqual(code, 0)
        installer.assert_not_called()

    def test_install_is_skipped_on_non_windows(self) -> None:
        """
        Ensures Linux users are pointed at their package manager instead.
        """

        with patch("src.paths.is_windows", return_value=False):
            self.assertFalse(install_for_current_user(Path("/project")))


class TestTesseractDiscovery(unittest.TestCase):
    """
    Verifies that the per-user copy is actually used at runtime.
    """

    def test_path_wins_when_tesseract_is_installed_normally(self) -> None:
        """
        Ensures an existing install keeps being used.
        """

        from src.platform import resolve_tesseract_path

        with patch("src.platform.which", return_value=r"C:\Tools\tesseract.exe"):
            self.assertEqual(resolve_tesseract_path(), r"C:\Tools\tesseract.exe")

    def test_the_private_copy_is_found_without_path_entry(self) -> None:
        """
        Ensures a per-user install works without touching PATH.

        Changing the system PATH is exactly what an account without
        administrator rights cannot do.
        """

        from src import platform as platform_module

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            executable = bundled_tesseract_exe(project)
            executable.parent.mkdir(parents=True)
            executable.write_text("stub")

            with patch.object(platform_module, "which", return_value=None), patch(
                "src.paths.is_windows", return_value=True
            ), patch(
                "src.tesseract_setup.bundled_tesseract_exe", return_value=executable
            ):
                self.assertEqual(
                    platform_module.resolve_tesseract_path(), str(executable)
                )

    def test_nothing_found_reports_none(self) -> None:
        """
        Ensures a machine without OCR degrades instead of failing.
        """

        from src import platform as platform_module

        with patch.object(platform_module, "which", return_value=None), patch(
            "src.paths.is_windows", return_value=False
        ):
            self.assertIsNone(platform_module.resolve_tesseract_path())

    def test_ocr_returns_empty_text_without_tesseract(self) -> None:
        """
        Ensures the OCR tool stays harmless when nothing is installed.
        """

        from src.ocr import extract_text_from_png_bytes

        with patch("src.ocr.resolve_tesseract_path", return_value=None):
            self.assertEqual(extract_text_from_png_bytes(b"not-a-png"), "")


if __name__ == "__main__":
    unittest.main()
