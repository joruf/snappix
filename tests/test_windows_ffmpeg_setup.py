"""
Tests for installing ffmpeg on Windows without administrator rights.

The winget package installs machine-wide and prompts for elevation, which fails
outright on a locked-down account -- taking video recording and MP4/GIF export
with it. The replacement is a ZIP that Python unpacks, so nothing is executed
and nobody is prompted.

Windows is simulated; no test here needs to run on Windows.
"""

from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import install_dependencies
from src.ffmpeg_setup import (
    REQUIRED_EXECUTABLES,
    bundled_ffmpeg_dir,
    bundled_ffmpeg_exe,
    extract_executables,
    has_bundled_ffmpeg,
    install_for_current_user,
    vendored_archive,
)


def _archive(path: Path, *, prefix: str = "ffmpeg-n9.0-latest-win64-gpl-9.0") -> Path:
    """
    Builds a stand-in archive shaped like the real ffmpeg download.

    Args:
        path: Archive to write.
        prefix: Version-named top-level directory, as the real build has.

    Returns:
        Path: The written archive.
    """

    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(f"{prefix}/bin/ffmpeg.exe", b"MZ-ffmpeg")
        bundle.writestr(f"{prefix}/bin/ffprobe.exe", b"MZ-ffprobe")
        bundle.writestr(f"{prefix}/bin/ffplay.exe", b"MZ-ffplay")
        bundle.writestr(f"{prefix}/LICENSE.txt", b"GPL")
    return path


class TestArchiveExtraction(unittest.TestCase):
    """
    Verifies unpacking, which is what avoids running an installer at all.
    """

    def test_both_needed_executables_are_written(self) -> None:
        """
        Ensures ffprobe comes along: importing a video reads its size with it.
        """

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = _archive(root / "ffmpeg.zip")
            target = root / "out"

            written = extract_executables(archive, target)

            self.assertEqual(
                sorted(path.name for path in written), sorted(REQUIRED_EXECUTABLES)
            )
            for name in REQUIRED_EXECUTABLES:
                self.assertTrue((target / name).is_file())

    def test_the_version_directory_is_flattened_away(self) -> None:
        """
        Ensures the install path does not change with every ffmpeg release.

        The archive nests everything under a version-named directory; keeping it
        would move the executable on each update and break the lookup.
        """

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = _archive(root / "ffmpeg.zip", prefix="ffmpeg-n42.7-win64-gpl")
            target = root / "out"

            extract_executables(archive, target)

            self.assertTrue((target / "ffmpeg.exe").is_file())
            self.assertFalse((target / "ffmpeg-n42.7-win64-gpl").exists())

    def test_ffplay_is_left_out(self) -> None:
        """
        Ensures the unused player is not unpacked; it costs well over 100 MB.
        """

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = _archive(root / "ffmpeg.zip")
            target = root / "out"

            extract_executables(archive, target)

            self.assertFalse((target / "ffplay.exe").exists())

    def test_an_archive_without_ffmpeg_is_rejected(self) -> None:
        """
        Ensures a wrong or truncated download fails loudly.
        """

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "wrong.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("readme.txt", b"nothing useful")

            with self.assertRaises(OSError):
                extract_executables(archive, root / "out")

    def test_completeness_needs_every_executable(self) -> None:
        """
        Ensures a half-unpacked copy is not mistaken for a working one.
        """

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            directory = bundled_ffmpeg_dir(project)
            directory.mkdir(parents=True)
            (directory / "ffmpeg.exe").write_text("stub")

            self.assertFalse(has_bundled_ffmpeg(project))

            (directory / "ffprobe.exe").write_text("stub")
            self.assertTrue(has_bundled_ffmpeg(project))


class TestVendoredArchive(unittest.TestCase):
    """
    Verifies the pre-fetched archive is used when present.
    """

    def test_a_prefetched_archive_is_picked_up(self) -> None:
        """
        Ensures ``scripts/fetch_ffmpeg_windows.py`` enables an offline install.
        """

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            archive = project / "vendor" / "ffmpeg-windows.zip"
            archive.parent.mkdir(parents=True)
            _archive(archive)

            self.assertEqual(vendored_archive(project), archive)

    def test_absence_is_reported_as_none(self) -> None:
        """
        Ensures the installer knows it has to download instead.
        """

        with TemporaryDirectory() as temporary:
            self.assertIsNone(vendored_archive(Path(temporary)))

    def test_install_uses_the_prefetched_archive_without_network(self) -> None:
        """
        Ensures no download happens when the archive is already there.
        """

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            archive = project / "vendor" / "ffmpeg-windows.zip"
            archive.parent.mkdir(parents=True)
            _archive(archive)

            with patch("src.paths.is_windows", return_value=True), patch(
                "src.ffmpeg_setup._download_current_archive"
            ) as download:
                self.assertTrue(install_for_current_user(project))

            download.assert_not_called()
            self.assertTrue(has_bundled_ffmpeg(project))

    def test_install_is_skipped_on_non_windows(self) -> None:
        """
        Ensures Linux users are pointed at their package manager instead.
        """

        with patch("src.paths.is_windows", return_value=False):
            self.assertFalse(install_for_current_user(Path("/project")))


class TestNoElevationDuringSetup(unittest.TestCase):
    """
    Verifies ordinary setup can no longer trigger an elevation prompt.
    """

    def test_no_winget_package_is_installed_automatically(self) -> None:
        """
        Ensures nothing machine-wide is installed behind the user's back.

        Both former entries -- ffmpeg and Tesseract -- prompted for elevation.
        """

        self.assertEqual(install_dependencies.WINDOWS_WINGET_PACKAGES, {})

    def test_windows_setup_requires_nothing(self) -> None:
        """
        Ensures setup cannot fail on an account without administrator rights.
        """

        with patch("src.paths.is_windows", return_value=True), patch.object(
            install_dependencies, "which", return_value=None
        ):
            self.assertEqual(
                install_dependencies.detect_missing_system_dependencies(), []
            )

    def test_the_opt_in_command_installs_per_user(self) -> None:
        """
        Ensures ``--install-ffmpeg`` uses the ZIP path, not winget.
        """

        with patch(
            "src.ffmpeg_setup.install_for_current_user", return_value=True
        ) as installer, patch(
            "src.video_recorder.has_ffmpeg", return_value=False
        ), patch("src.paths.is_windows", return_value=True):
            code = install_dependencies.install_ffmpeg_for_current_user(Path("/p"))

        self.assertEqual(code, 0)
        installer.assert_called_once()

    def test_existing_ffmpeg_is_left_alone(self) -> None:
        """
        Ensures an ffmpeg already on the machine is not duplicated.
        """

        with patch("src.video_recorder.has_ffmpeg", return_value=True), patch(
            "src.ffmpeg_setup.install_for_current_user"
        ) as installer:
            code = install_dependencies.install_ffmpeg_for_current_user(Path("/p"))

        self.assertEqual(code, 0)
        installer.assert_not_called()


class TestDiscovery(unittest.TestCase):
    """
    Verifies the per-user copy is found without touching PATH.
    """

    def test_bundled_ffmpeg_is_found(self) -> None:
        """
        Ensures the unpacked copy is used; changing PATH system-wide is exactly
        what an account without administrator rights cannot do.
        """

        from src import video_recorder

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            executable = bundled_ffmpeg_exe(project)
            executable.parent.mkdir(parents=True)
            executable.write_text("stub")

            with patch.object(video_recorder, "which", return_value=None), patch(
                "src.paths.is_windows", return_value=True
            ), patch(
                "src.ffmpeg_setup.bundled_ffmpeg_dir", return_value=executable.parent
            ):
                self.assertEqual(
                    video_recorder.resolve_ffmpeg_path(), str(executable)
                )

    def test_bundled_ffprobe_is_found(self) -> None:
        """
        Ensures importing a video also works with the per-user copy.
        """

        from src import ffmpeg_setup

        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            probe = bundled_ffmpeg_dir(project) / "ffprobe.exe"
            probe.parent.mkdir(parents=True)
            probe.write_text("stub")

            with patch("src.ffmpeg_setup.which", return_value=None), patch(
                "src.paths.is_windows", return_value=True
            ), patch.object(
                ffmpeg_setup, "bundled_ffmpeg_dir", return_value=probe.parent
            ):
                self.assertEqual(ffmpeg_setup.resolve_ffprobe_path(), str(probe))

    def test_path_still_wins(self) -> None:
        """
        Ensures an existing system install keeps being used.
        """

        from src import video_recorder

        with patch.object(
            video_recorder, "which", return_value=r"C:\Tools\ffmpeg.exe"
        ):
            self.assertEqual(
                video_recorder.resolve_ffmpeg_path(), r"C:\Tools\ffmpeg.exe"
            )


if __name__ == "__main__":
    unittest.main()
